# log_container


## Overview

`log_container` is a Python script that runs a bash command in a specified Docker image and
sends the logs to AWS CloudWatch Logs.

## Usage

Here's some examples:

```
python log_container.py --docker-image python \
--bash-command $'pip install pip -U && pip install tqdm && python -u -c \"import time\ncounter = 0\nwhile True:\n\tprint(counter)\n\tcounter = counter + 1\n\ttime.sleep(0.1)\"' \
--aws-cloudwatch-group test-task-group-1 \
--aws-cloudwatch-stream test-task-stream-1 \
--aws-access-key-id $AWS_ACCESS_KEY_ID \
--aws-secret-access-key $AWS_SECRET_ACCESS_KEY \
--awsregion us-east-1
```

```
python log_container.py --docker-image ubuntu \
--bash-command 'cat /etc/passwd' \
--aws-cloudwatch-group test-task-group-1 \
--aws-cloudwatch-stream test-task-stream-1 \
--aws-access-key-id $AWS_ACCESS_KEY_ID \
--aws-secret-access-key $AWS_SECRET_ACCESS_KEY \
--awsregion us-east-1
```

## Notes

* No sensible support for interactive commands
* If you don't see the logs, ensure the program doesn't buffer the stdout (e.g. run `python -u`)
