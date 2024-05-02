count=0
average=0
while read -r line; do
    # Check for the real time output from the time command
    if [[ $line == real* ]]; then
        if [ "$count" -eq 0 ]; then
            # Skip first result
            count=$((count+1))
            continue
        fi
        count=$((count+1))
        # Extract the minutes and seconds and convert to seconds
        minutes=$(echo $line | cut -d'm' -f1 | sed 's/real //')
        seconds=$(echo $line | cut -d'm' -f2 | cut -d's' -f1)
        total_seconds=$(echo "$minutes*60 + $seconds" | bc)
        # Accumulate the total time
        average=$(echo "$average + $total_seconds" | bc)
    fi
done < <(cat "$output_file")  # start reading from the 2nd run

# Subtract one from the count to account for the skipped first result
count=$((count-1))
# Compute the average time
average=$(echo "$average / $count" | bc)
count=0
while read -r line; do
    # Check for the real time output from the time command
    if [[ $line == real* ]]; then
        if [ "$count" -eq 0 ]; then
            # Skip first result
            count=$((count+1))
            continue
        fi
        count=$((count+1))
        # Extract the minutes and seconds and convert to seconds
        minutes=$(echo $line | cut -d'm' -f1 | sed 's/real //')
        seconds=$(echo $line | cut -d'm' -f2 | cut -d's' -f1)
        total_seconds=$(echo "$minutes*60 + $seconds" | bc)
        # Accumulate the total time
        average=$(echo "$average + $total_seconds" | bc)
    fi
done < <(cat "$output_file")  # start reading from the 2nd run

# Subtract one from the count to account for the skipped first result
count=$((count-1))
# Compute the average time
average=$(echo "scale=2; $average/$count" | bc)

# Print the average time
echo "Average total time (from 2nd to 5th run): $average seconds"
