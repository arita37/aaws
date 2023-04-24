""""

Atomic and concurrent write on S3


"""

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
bucket_name = 'my-bucket'
data_object_key = 'my-data.csv'
lock_object_key = data_object_key +'-lock'


def acquire_lock(dir_s3):
    try:
        s3.put_object(Bucket=bucket_name, Key=lock_object_key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucket':
            print(f'Bucket {bucket_name} does not exist')
        else:
            print(f'Failed to acquire lock: {e}')
        return False

def release_lock(dir_s3):
    try:
        s3.delete_object(Bucket=bucket_name, Key=lock_object_key)
    except ClientError as e:
        print(f'Failed to release lock: {e}')

        
def atomic_write(dir_s3, data):
    if acquire_lock():
        try:
            s3.put_object(Bucket=bucket_name, Key=data_object_key, Body=data)
        finally:
            release_lock()

def test():            
   data = b'some data to write'
   atomic_write(data)

  
  
