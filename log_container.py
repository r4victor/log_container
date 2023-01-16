import argparse
import json
import queue
import sys
from threading import Thread
import time
from typing import Iterable

import boto3
from botocore.client import BaseClient
import botocore.exceptions
import docker
import docker.errors


SEND_LOGS_INTERVAL = 5


def log_container(
    image_name: str,
    command: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
    awsregion: str,
    aws_cloudwatch_group: str,
    aws_cloudwatch_stream: str
):
    logs_client = get_logs_client(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        awsregion=awsregion,
    )

    try:
        create_log_group(logs_client, aws_cloudwatch_group)
        create_log_stream(logs_client, aws_cloudwatch_group, aws_cloudwatch_stream)
    except (botocore.exceptions.ClientError, botocore.exceptions.ConnectionError) as e:
        print(e)
        exit(1)

    try:
        client = docker.from_env()
    except docker.errors.DockerException:
        print('Error: ensure docker daemon is running')
        exit(1)

    try:
        container = client.containers.run(
            image_name, ['bash', '-c', command], detach=True, stderr=True
        )
    except docker.errors.APIError as e:
        print(e)
        exit(1)

    stdout = container.logs(stdout=True, stderr=False, stream=True)
    stderr = container.logs(stdout=False, stderr=True, stream=True)
    
    print('Container is running...')

    # We use threads to read from stdout/stderr concurrently in a portable manner
    q = queue.Queue()
    producers = [
        Thread(target=produce_log_messages, args=[q, stdout, 'stdout', command]),
        Thread(target=produce_log_messages, args=[q, stderr, 'stderr', command]),
    ]
    for producer in producers:
        producer.start()

    death_pills_num = 0
    total_logs_sent = 0
    logs_batch = []
    last_sent_time = time.time()
    try:
        while container.status == 'running' or death_pills_num != len(producers) or len(logs_batch) > 0:
            try:
                log_message = q.get(timeout=1)
            except queue.Empty:
                pass
            else:
                if log_message is None:
                    death_pills_num += 1
                else:
                    print(log_message['data'])
                    log = {
                        # We construct timestamps in the main thread because
                        # `put_log_events` requires them to be ordered
                        'timestamp': int(time.time() * 1000),
                        'message': json.dumps(log_message),
                    }
                    logs_batch.append(log)
            if len(logs_batch) > 0 and time.time() - last_sent_time > SEND_LOGS_INTERVAL:
                logs_client.put_log_events(
                    logGroupName=aws_cloudwatch_group,
                    logStreamName=aws_cloudwatch_stream,
                    logEvents=logs_batch,
                )
                total_logs_sent += len(logs_batch)
                logs_batch = []
                last_sent_time = time.time()
    except KeyboardInterrupt:
        try:
            print('Stopping container...')
            container.stop()
        except KeyboardInterrupt:
            print('Killing container...')
            container.kill()
    container.remove()
    print(f'Sent {total_logs_sent} logs')
    print('Done')


def get_logs_client(
    aws_access_key_id: str,
    aws_secret_access_key: str,
    awsregion: str,
) -> BaseClient:
    return boto3.client(
        'logs',
        region_name=awsregion,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )


def create_log_group(logs_client: BaseClient, aws_cloudwatch_group: str):
    try:
        logs_client.create_log_group(logGroupName=aws_cloudwatch_group)
    except logs_client.exceptions.ResourceAlreadyExistsException:
        pass
    else:
        print(f'Log group "{aws_cloudwatch_group}" has been created')


def create_log_stream(logs_client: BaseClient, aws_cloudwatch_group: str, aws_cloudwatch_stream: str):
    try:
        logs_client.create_log_stream(
            logGroupName=aws_cloudwatch_group,
            logStreamName=aws_cloudwatch_stream,
        )
    except logs_client.exceptions.ResourceAlreadyExistsException:
        pass
    else:
        print(f'Log stream "{aws_cloudwatch_group}" has been created')


def produce_log_messages(q: queue.Queue, source: Iterable[bytes], source_name: str, command: str):
    for line in source:
        message = {
            'command': command,
            'source': source_name,
            'data': line.decode().rstrip('\n'),
        }
        q.put(message)
    q.put(None)


def main():
    parser = argparse.ArgumentParser(
        description=(
            'A script that runs a bash command in a specified Docker image '
            'and sends the logs to AWS CloudWatch Logs.'
        )
    )
    parser.add_argument('--docker-image', required=True)
    parser.add_argument('--bash-command', required=True)
    parser.add_argument('--aws-access-key-id', required=True)
    parser.add_argument('--aws-secret-access-key', required=True)
    parser.add_argument('--awsregion', required=True)
    parser.add_argument('--aws-cloudwatch-group', required=True)
    parser.add_argument('--aws-cloudwatch-stream', required=True)
    args = parser.parse_args(sys.argv[1:])

    log_container(
        image_name=args.docker_image,
        command=args.bash_command,
        aws_access_key_id=args.aws_access_key_id,
        aws_secret_access_key=args.aws_secret_access_key,
        awsregion=args.awsregion,
        aws_cloudwatch_group=args.aws_cloudwatch_group,
        aws_cloudwatch_stream=args.aws_cloudwatch_stream,
    )


if __name__ == '__main__':
    main()
