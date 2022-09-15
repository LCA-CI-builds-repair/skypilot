from absl import app
from absl import flags
from absl import logging

import sys
import time

import tensorflow_datasets as tfds
import tensorflow as tf
import tensorflow_text as tf_text
from transformers import TFDistilBertForSequenceClassification
from transformers import TFBertForSequenceClassification
from transformers import pipeline

from preprocess import preprocessing_fn, preprocess_bert_input, get_example_input
"""
# Train on TPU
python -u run_tpu.py \
--tpu $TPU_NAME \
--data_dir gs://skypilot-pii-annonymized-dataset \
--model_dir gs://skypilot-pipeline-b-model \
--num_epochs 1 \
--mode=train --amp --xla

# Inference on TPU
python -u run_tpu.py \
--tpu $TPU_NAME \
--model_dir gs://skypilot-pipeline-b-model \
--num_epochs 1 \
--per_core_batch_size 1 \
--mode=infer
"""

flags.DEFINE_string('tpu', default=None, help='tpu name')
flags.DEFINE_integer('per_core_batch_size',
                     default=32,
                     help='batch size for each core')
flags.DEFINE_integer('num_cores', default=8, help='number of cores to use')
flags.DEFINE_string('data_dir', default=None, help='path to the dataset')
flags.DEFINE_string('model_dir', default=None, help='path to the model')
flags.DEFINE_integer('num_epochs', default=5, help='num epochs')
flags.DEFINE_boolean('amp', default=False, help='use amp')
flags.DEFINE_boolean('xla', default=False, help='use xla')
flags.DEFINE_integer('infer_sentences',
                     default=1000000,
                     help='number of sentences to infer')
flags.DEFINE_enum('mode',
                  'train', ['train', 'infer'],
                  help='Mode to run: train or infer.')
FLAGS = flags.FLAGS

SAVED_MODEL_LENGTH = 384


def save_model(model, model_dir):
    a = tf.constant([list(range(1, SAVED_MODEL_LENGTH + 1))], dtype=tf.int64)
    b = tf.constant([[1] * SAVED_MODEL_LENGTH], dtype=tf.int64)
    inp = {"input_ids": a, "attention_mask": b}
    model._saved_model_inputs_spec = None
    model._set_save_spec(inp)
    model.save(model_dir)


def main(unused):
    use_gpu = (FLAGS.tpu is not None and FLAGS.tpu.lower() == 'gpu')
    if use_gpu:
        strategy = tf.distribute.experimental.MultiWorkerMirroredStrategy(
            communication=tf.distribute.experimental.CollectiveCommunication.
            NCCL)
    else:
        resolver = tf.distribute.cluster_resolver.TPUClusterResolver(
            tpu=FLAGS.tpu)
        tf.config.experimental_connect_to_cluster(resolver)
        tf.tpu.experimental.initialize_tpu_system(resolver)
        strategy = tf.distribute.experimental.TPUStrategy(resolver)
    assert use_gpu or (not FLAGS.amp and
                       not FLAGS.xla), 'AMP and XLA only supported on GPU.'
    if use_gpu:
        # From Nvidia Repo, explained here: htteps://github.com/NVIDIA/DeepLearningExamples/issues/57
        os.environ['CUDA_CACHE_DISABLE'] = '0'
        os.environ['TF_GPU_THREAD_MODE'] = 'gpu_private'
        os.environ['TF_GPU_THREAD_COUNT'] = '2'
        os.environ['TF_USE_CUDNN_BATCHNORM_SPATIAL_PERSISTENT'] = '1'
        os.environ['TF_ADJUST_HUE_FUSED'] = '1'
        os.environ['TF_ADJUST_SATURATION_FUSED'] = '1'
        os.environ['TF_ENABLE_WINOGRAD_NONFUSED'] = '1'
        os.environ['TF_SYNC_ON_FINISH'] = '0'
        os.environ['TF_AUTOTUNE_THRESHOLD'] = '2'
        os.environ['TF_DISABLE_NVTX_RANGES'] = '1'
    if FLAGS.xla:
        # https://github.com/tensorflow/tensorflow/blob/8d72537c6abf5a44103b57b9c2e22c14f5f49698/tensorflow/compiler/jit/flags.cc#L78-L87
        # 1: on for things very likely to be improved
        # 2: on for everything
        # fusible: only for Tensorflow operations that XLA knows how to fuse
        #
        # os.environ['TF_XLA_FLAGS'] = '--tf_xla_auto_jit=1'
        # os.environ['TF_XLA_FLAGS'] = '--tf_xla_auto_jit=2'
        # Best Performing XLA Option
        os.environ['TF_XLA_FLAGS'] = '--tf_xla_auto_jit=fusible'
        os.environ["TF_XLA_FLAGS"] = (os.environ.get("TF_XLA_FLAGS", "") +
                                      " --tf_xla_enable_lazy_compilation=false")

    if FLAGS.mode != 'infer':
        ds_train, ds_info = tfds.load('amazon_us_reviews/Books_v1_02',
                                      split='train[:5%]',
                                      with_info=True,
                                      download=False,
                                      data_dir=FLAGS.data_dir)

    if FLAGS.mode != 'infer':
        from transformers import BertTokenizerFast

        tokenizer = BertTokenizerFast.from_pretrained('bert-base-uncased')

        def dataset_fn(ds):
            return ds.filter(lambda x: x['data']['helpful_votes'] >= 7)

        ds_train_filtered = ds_train.apply(dataset_fn)

        def process(example):
            return (dict(tokenizer(
                example['data']['review_body'].numpy().decode('utf-8')),
                         truncation=True,
                         padding=True), example['data']['star_rating'].numpy())

        def process_py(inp1, inp2):
            return [
                dict(tokenizer(inp1.numpy().decode('utf-8')),
                     truncation=True,
                     padding=True),
                inp2.numpy()
            ]

        ds_train_filtered_2 = ds_train_filtered.map(preprocessing_fn)

        batch_size = FLAGS.per_core_batch_size * FLAGS.num_cores
        inuse_dataset = ds_train_filtered_2.shuffle(1000).batch(
            batch_size).prefetch(tf.data.experimental.AUTOTUNE)

    if not use_gpu:
        tf.keras.mixed_precision.experimental.set_policy('mixed_bfloat16')
    if FLAGS.amp:
        policy = tf.keras.mixed_precision.experimental.Policy('mixed_float16')
        tf.keras.mixed_precision.experimental.set_policy(policy)

    if FLAGS.mode == 'infer':
        with strategy.scope():
            original_model = TFBertForSequenceClassification.from_pretrained(
                'bert-base-uncased', num_labels=1)
            model = tf.keras.models.load_model(
                FLAGS.model_dir,
                custom_objects={'compute_loss': original_model.compute_loss})

        #Our example data!
        example_input = get_example_input(FLAGS.per_core_batch_size)

        @tf.function
        def infer_step(example):

            def infer_fn(example):
                predictions = model(example, training=False)['logits']
                predictions = tf.cast(predictions, tf.float32)
                return predictions

            values = strategy.run(infer_fn, args=(example,))
            if FLAGS.num_cores == 1:
                return values
            return strategy.gather(values, axis=0)

        logging.info('Starting inference...')
        batch_size = FLAGS.per_core_batch_size * FLAGS.num_cores
        total_steps = FLAGS.infer_sentences // batch_size
        warmup_inf_steps = 20
        counter = 0
        inf_times = []
        import numpy as np
        shapes = []
        while counter < total_steps + warmup_inf_steps:
            start_time = time.time()
            batch = infer_step(example_input)
            shapes.append(batch.numpy().shape)
            end_time = time.time()
            if counter > warmup_inf_steps:
                inf_times.append(end_time - start_time)
            counter += 1
            if counter % 1000 == 0:
                logging.info(
                    'Evaluation Iter ' + str(counter) +
                    f'\nMean Latency: {np.mean(inf_times) * 1000:.2f} ms')
            if counter >= total_steps + warmup_inf_steps:
                break
        inf_times = np.array(inf_times)
        import pandas as pd
        throughput = FLAGS.infer_sentences / np.sum(inf_times)
        mean_latency = 1000.0 * np.mean(inf_times)
        P90_latency = 1000.0 * np.percentile(inf_times, 90)
        P99_latency = 1000.0 * np.percentile(inf_times, 99)

        df = pd.DataFrame({
            'batch_size': [batch_size],
            'throughput': [throughput],
            'p90_ms': [P90_latency],
            'p99_ms': [P99_latency],
            'mean_ms': [mean_latency],
            'num_images': [(counter - warmup_inf_steps) * batch_size],
        })
        print(shapes[0])
        print(df)
        df.to_csv(f'results-{batch_size}.csv', index=False, header=True)
        return

    with strategy.scope():
        model = TFBertForSequenceClassification.from_pretrained(
            'bert-base-uncased', num_labels=1)

        optimizer = tf.keras.optimizers.Adam(learning_rate=5e-5)
        if FLAGS.amp:
            optimizer = tf.keras.mixed_precision.LossScaleOptimizer(optimizer)
        model.compile(optimizer=optimizer,
                      loss=model.compute_loss)  # can also use any keras loss fn
        model.summary()

    save_model(model, FLAGS.model_dir)
    model.fit(inuse_dataset, epochs=FLAGS.num_epochs, batch_size=batch_size)
    logging.info('Saving. This might take a while...')
    save_model(model, FLAGS.model_dir)

    # saved_weights_path = os.path.join(FLAGS.model_dir, 'saved_weights.h5')
    # # Copy model.h5 over to Google Cloud Storage
    # with file_io.FileIO('saved_weights.h5', mode='rb') as input_f:
    #     with file_io.FileIO(saved_weights_path, mode='wb+') as output_f:
    #         output_f.write(input_f.read())
    #     logging.info(f'Saved model weights to {saved_weights_path}...')


if __name__ == '__main__':
    logging.set_verbosity(logging.INFO)
    app.run(main)
