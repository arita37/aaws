# -*- coding: utf-8 -*-
""" Utils for AWS
Docs::

   pip install awswrangler
   https://aws-sdk-pandas.readthedocs.io/en/stable/stubs/awswrangler.s3.wait_objects_exist.html


   pip install ijson   #Streaming JSON
   https://pythonspeed.com/articles/json-memory-streaming/


"""
import os, sys, time, datetime, gc, io, functools
from pathlib import Path
from typing import Union, IO,Tuple, Dict, List, Optional
import boto3, fire, pandas as pd, numpy as np
#import orjson as  json
import json
import awswrangler as wr
import subprocess
######################################################################################
from utilmy import log, log2, log3, loge, logw
from utilmy import (os_system, date_now, os_path_norm, os_makedirs, glob_glob, glob_filter_dirlevel,
 glob_filter_filedate, pd_to_file
)

######################################################################################
def test_oscopys3():
    ymd = date_now(fmt="%Y%m%d")
    # dirin="ztmp/ctr/latest/data/"
    dirin  = "s3://a/ztmp/20230325/"
    dirout = f"s3://a/ztmp/{ymd}_b"    
    os_copy_s3(dirin, dirout, dryrun=False)




########################################################################################################
########################################################################################################
def aws_logfetch(dtstart=None, dtend=None, logroup:str=None, logstream:str=None , dirout='mylog.csv',
    add_hours_start=-1,
    add_hours_end=0,
    timezone='Asia/Japan',
    query_tag='myquery_name',
    nmax=1000

 ):
    """
        alias aaws="python util_aws.py"

        aaws aws_logfetch --dtstart 20230414-1200  --dtend 20230414-1500 --logroup mygroup  --logstream mystream

        export aws_loggroup=mygroup
        export aws_loggroup=mystream        
        export aws_logqueries_file=myqueries.json               
        aaws  aws_logfetch  --add_hours_start -5     ## from -5hours to now


         myqueries.json
         {
              "query1" :  "fields @timestamp, @message | filter @logStream like '{logstream}' | fields time,log # , tomillis(@timestamp) as millis | filter log like 'CKS;' | limit {nmax} "

             ,"query1" :  "fields @timestamp, @message | filter @logStream like '{logstream}' | fields time,log # , tomillis(@timestamp) as millis | filter log like 'CKS;' | limit {nmax} "

         }


    """
    from utilmy import os_system, date_now, os_makedirs, json_load

    logroup  = os.environ['aws_logroup']     if logroup   is None  else logroup 
    logsteam = os.environ['aws_stream']      if logstream is None  else logstream
    timezone = os.environ['aws_timezone']    if timezone  is None  else timezone

    dt_start1 = date_now(dtstart, add_hours=add_hours_start, fmt_input="%Y%m%d-%H%M", timezone=timezone ,returnval='unix')
    dt_end1   = date_now(dtend,   add_hours=add_hours_end,   fmt_input="%Y%m%d-%H%M", timezone=timezone ,returnval='unix')
    log(dt_start1, dt_end1)

    ### TODO define queries if it works
    qstr0 ="""fields @timestamp, @message | filter @logStream like '{logstream}' | fields time,log #  | filter log like '' | limit {nmax} """

    try : 
       query_dict = json_load(os.environ.get('aws_logqueries_file', 'myqueries.json')) 
    except :
       query_dict = {}

    qstr = query_dict.get(query_tag, qstr0)
    if 'logstream' in qstr: qstr = qstr.format(logstream=logstream)
    if '{nmax}' in qstr:    qstr = qstr.format(nmax=nmax)


    ### AWS CLI command to start the query with specified parameters
    cmd = f""" aws logs start-query --log-group-name {logroup} --start-time {dt_start1}  --end-time {dt_end1} --query-string \"{qstr}\" """
    # log(cmd)
    output, err = os_system(cmd)
    data = json.loads(output)
    query_id=data['queryId']
    log("query_id:" query_id)

    ### AWS CLI command to get the query results and save them to a file
    cmd = f'aws logs get-query-results --query-id {query_id} | jq -r \'.results[] | map(.value) | @csv\' >  {dirout} '
    os_makedirs(dirout)
    log(cmd)
    os.system(cmd)



def s3_config_load(dirs3:str, mode='rb')->Dict:
   """ load JSON config in ddict from Local or from S3

   :param dirs3:  S3 path or Local path
   :param mode:   rb by default
   :return:
   """
   from smart_open import open

   try :
        if "s3:/" in dirs3:
          session = aws_get_session()
          with open(dirs3, mode=mode, transport_params={'client': session.client("s3")}  ) as fp:
             ddict = json.load(fp)
        else :
          with open(dirs3, mode=mode,  ) as fp:
             ddict = json.load(fp)

        return ddict
   except Exception as e:
        logw(f"####s3_config_load, cannot read {dirs3}")
        logw(e)
        return None


def os_copy(src, dst, verbose=0):
    import shutil

    if os.path.isfile(src):
       shutil.copy2(src, dst)
       log("copy done")
       return None

    if not os.path.exists(dst):
        os_makedirs(dst)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if verbose: log(s, d)
        try :
            if os.path.isdir(s):
                shutil.copytree(s, d, False, None)
            else:
                shutil.copy2(s, d)
        except Exception as e:
            log(e)
    log("copy done")


def os_copy_s3(dirin:str, dirout:str, dryrun=False, recursive=True, exclude='*DS_Store',  max_try=3):
    """  Copy folders on local OR on S3
    Docs::

         aws s3 mv s3://test/customers/ s3://test/customers/EU/ --recursive --exclude "*" --include "*EU_GR*" --exclude "*/EU/*"
    """
    if "s3:/" not in dirout :
        os_copy(dirin, dirout)

    dirin      = s3_path_norm(dirin)
    dirout_s3b = s3_path_norm( dirout)

    isfile= False
    if "." in dirin.split("/")[-1]:
        isfile= True
   
    #cmd = f"aws s3 sync  '{dirin}'  '{dirout_s3b}'  "   #### Sync is already recursive
    cmd = f"aws s3 cp  '{dirin}'  '{dirout_s3b}'  "
    if recursive and not isfile :  cmd += "  --recursive "
    if dryrun :    cmd += "  --dryrun    "
    if exclude :   cmd += f" --exclude '{exclude}' "

    if not isfile:
       s3_makedirs(dir_s3=  dirout_s3b )

    log2(cmd)
    out,err, isok = os_system_retry(cmd, max_try= max_try)
    log(out, err)
    if isok:
        log(f'Success Copied to S3: {dirout_s3b}')


def s3_move_tos3(dirin:str, dirout_s3:str, dryrun=False, recursive=True,  max_try=3):
    """  Move folders from Local to S3
    Docs::

         aws s3 mv s3://test/customers/ s3://test/customers/EU/ --recursive --exclude "*" --include "*EU_GR*" --exclude "*/EU/*"
    """
    if "s3:/" not in dirout_s3 :
        log(f"s3_move_tos3: Local folder only, not move {dirin}")
        return 

    dirin      = os_path_norm(dirin)
    folder     = dirin.split("/")[-2]
    dirout_s3b = s3_path_norm( dirout_s3 + "/" + folder )
    
    cmd = f"aws s3 mv  '{dirin}'  '{dirout_s3b}'  "
    if recursive:  cmd += "  --recursive "
    if dryrun :    cmd += "  --dryrun    "
     
    s3_makedirs(dir_s3=  dirout_s3b )

    log2(cmd)
    out,err, isok = os_system_retry(cmd, max_try= max_try)
    log(out, err)
    if isok:
        log(f'Success moved to S3: {dirout_s3b}')


def s3_copy_tolocal(dirin_s3:str, dirout:str, dryrun=False, recursive=True,  max_try=3, exclude=None,  path_mode='unix'):
    """  Move folders from Local to S3
    Docs::

         aws s3 sync s3://test/customers/ s3://test/customers/EU/ --recursive --exclude "*" --include "*EU_GR*" --exclude "*/EU/*"
    """
    dirin   = os_path_norm(dirin_s3)

    if path_mode == 'unix':
       folder  = dirin.split("/")[-2] if dirin[-1] == "/"  else  dirin.split("/")[-1]
       diroutb = dirout + "/" + folder
    else :
       diroutb = dirout

    cmd = f"aws s3 sync  '{dirin_s3}'  '{diroutb}'  "
    # if recursive:  cmd += "  --recursive "
    if dryrun :    cmd += "  --dryrun "
    if exclude :   cmd += f"  --exclude '{exclude}' "

    os_makedirs(diroutb )
    log(cmd) 
    out,err, isok = os_system_retry(cmd, max_try= max_try)
    if isok:
        log(f'Success Downloaded to: {diroutb}')


def os_system_retry(cmd, max_try=1):
    ii = 0
    out, err = "", ""
    while ii < max_try :
       out, err = os_system(cmd, doprint=True)
       if 'error' in err or 'Error' in err :
           ii = ii + 1
           time.sleep(ii*5)
       else :
           return out, err, True
    return out, err, False


def s3_copy_tolocal_bydate(dirin_s3:str, dirout:str, dryrun=False, recursive=True,  max_try=3, n_recent=2):
    """  Move folders from S3 to Local
    """
    if "s3:/" not in dirin_s3 :
        log(f"s3_copy_tolocal: Local folder only, not move {dirin_s3}")
        return 

    fdirs = glob_s3_dirs(dirin_s3)
    fdirs = [  di for di in fdirs if len(di.replace(dirin_s3, "")) >4  ]
    log2("S3 dirs:", fdirs)

    fdirs = sorted(fdirs)
    if len(fdirs)>0:
       dirs3_list = fdirs[-n_recent:]
       for dir_s3 in dirs3_list :
          s3_copy_tolocal(dirin_s3= dir_s3, dirout= dirout, dryrun=dryrun, recursive=recursive,  max_try= max_try)
    else :
       logw(f"Cannot copy from S3 to Local, No dirs for {dirin_s3}")

 
def s3_makedirs(dir_s3:str):
   """ Make S3 Sub-folders
   Docs:

        # created nested folder
        aws s3api put-object --bucket main_folder --key nested1/nested2/nested3/somefoldertosync

        # sync my local folder to s3
        aws s3 sync /home/ubuntu/somefoldertosync s3://main_folder/nested1/nested2/nested3/somefoldertosync

   """ 
   key, path = s3_split_path(dir_s3)
   cmd = f"aws s3api put-object --bucket '{key}'  --key '{path}' "
   log2(cmd)
   out, err = os_system(cmd)
   log(out)


def s3_path_norm(dirs3:str):
    return dirs3.replace("//", "/").replace("s3:/", "s3://") 



######################################################################################
def aws_check_session(session,)->bool:
    """ Check if an aws session works """
    try:
        session.client('sts').get_caller_identity()
        return True
    except:
        return False


def aws_check_session2(session,)->bool:
    """ Check if an aws session works """
    try:
        session.client('s3').list_buckets()
        return True
    except:
        return False


def s3_check_bucket(session, bucket_name=''):
    """ Check if an aws s3 bucket exist """
    s3 = session.resource('s3')
    try:
        s3.meta.client.head_bucket(Bucket=bucket_name)
        return True
    except:
        return False


##### List of JSON ######################################################################################
def aws_get_session(profile_name:str="", session=None):
    """ Get session
    Docs::
     
        1) From local cache  .aws/cli/cache .aws/cli/boto
        2) From ENV Variable: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
        Returns: Boto3 session
    """
    from botocore import credentials
    import botocore.session
    import glob, boto3

    if session is not None :
        return session

    if os.environ.get('USE_LOCALSTACK_BOTO3', "0") == "1" :
       import localstack_client.session as boto3 
       client = boto3.Session(botocore_session=session)
       return client

    for fi in [ '.aws/cli/cache', '.aws/boto/cache' ]:
        # By default the cache path is ~/.aws/boto/cache
        cli_cache = os.path.join(os.path.expanduser('~'), fi)
        if len(glob.glob(cli_cache + "/*" ) ) > 0 :
            # Construct botocore session with cache
            session = botocore.session.get_session()
            session.get_component('credential_provider').get_provider('assume-role').cache = credentials.JSONFileCache(cli_cache)

            # Create boto3 client from session
            client = boto3.Session(botocore_session=session)
            log2("Using ", fi, client)
            return client
 

    client = boto3.Session( aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID', None) ,
                            aws_secret_access_key= os.environ.get('AWS_SECRET', None),
                            region_name= os.environ.get('AWS_DEFAULT_REGION', 'ap-northeast-1'))

    log2("using ENV Variables ", client)
    return client



def s3_get_filelist(path_s3="/mybucket1/mybucket2/", suffix=".json"):
    """     # Get all json files in a S3 bucket
    Docs::
    
        path_s3_bucket (str, optional): _description_. Defaults to "/mybucket1/mybucket2/".
        suffix (str, optional): _description_. Defaults to ".json".
    Returns:  List of S3 filename
    """
    s3         = boto3.resource('s3')
    my_bucket  = s3.Bucket(path_s3)
    s3_objects = []
    for file in my_bucket.objects.all():
        # filter only json files
        if file.key.lower().find(suffix) != -1:
            fi =  f"s3://{path_s3}/{file.key}"
            s3_objects.append(fi)
    return s3_objects


def pl_read_file_s3(path_s3="s3://mybucket", suffix=None,npool=2, dataset=False,show=0, nrows=1000000000, session=None,
                    lower_level=0, upper_level=0,**kw):
    """ Read files into Polars
    """
    import polars as pl
    import pyarrow.parquet as pq
    import s3fs

    session = aws_get_session() 
    fs = s3fs.S3FileSystem(session=session)
    flist = fs.ls(path_s3)

    dfall= None
    for filei in flist:
        if filei.endswith(".parquet"):
            dataset = pq.ParquetDataset(filei, filesystem=fs)
            dfi = pl.from_arrow(dataset.read())
            dfall = pl.concat((dfall, dfi)) if dfall is not None else dfi
    print(dfall) 
    return dfall


##### s3 to JSON ######################################################################################
def s3_read_json(path_s3="", n_workers=1, verbose=True, suffix=".json",   **kw):
    """  Run Multi-processors load using smart_open
    Docs::

         pip install "smart_open[s3]==6.2.0"
         https://github.com/RaRe-Technologies/smart_open/blob/develop/howto.md#how-to-read-from-s3-efficiently 
         If run on Windows operating system, please move freeze_support to the main function
         As suggested here https://docs.python.org/3/library/multiprocessing.html#multiprocessing.freeze_support
    """
    from multiprocessing import freeze_support
    from smart_open import s3

    try :    
       freeze_support()
    except Exception as e : 
       log(e)   

    res_data = {}
    for key, content in s3.iter_bucket(path_s3, workers=n_workers, accept_key=lambda key: key.endswith(suffix)):
        res_data[path_s3 + "/" + key] =  json.loads(content)

    return res_data




def s3_json_read2(path_s3, npool=5, start_delay=0.1, verbose=True, input_fixed:dict=None, suffix=".json",  **kw):
    """  Run Multi-thread json reader for S3 json files, using smart_open in Mutlti Thread
    Doc::
    
         Return list of tuple  : (S3_path, ddict )
         https://github.com/RaRe-Technologies/smart_open/blob/develop/howto.md#how-to-read-from-s3-efficiently 
        

    """
    from smart_open import open

    ### Global Session, Shared across Threads
    session = boto3.Session()   
    client  = session.client('s3')

    def json_load(s3_path, verbose=True):
        if len(s3_path) == 0:
            return None
        else:
            s3_path = s3_path.pop()
        
        ### Thread Safe function to parallelize
        with open(s3_path, mode='r', transport_params={'client': client} ) as f:
            file_content = f.read()
        try:
            ddict = json.loads(file_content)
        except:
            ddict = {}
            
        return (s3_path, ddict)


    if input_fixed is not None:
        fun_async = functools.partial(json_load, **input_fixed)
    else :
        fun_async= json_load    

    input_list = s3_get_filelist(path_s3, suffix= suffix)


    #### Input xi #######################################
    xi_list = [[] for t in range(npool)]
    for i, xi in enumerate(input_list):
        jj = i % npool
        path_to_s3_object = xi
        #path_to_s3_object = f"s3://{path_s3}/{xi}"
        xi_list[jj].append( path_to_s3_object )

    if verbose:
        for j in range(len(xi_list)):
            log('thread ', j, len(xi_list[j]))
        # time.sleep(6)

    #### Pool execute ###################################
    import multiprocessing as mp
    # pool     = multiprocessing.Pool(processes=3)
    pool = mp.pool.ThreadPool(processes=npool)
    job_list = []
    for i in range(npool):
        time.sleep(start_delay)
        log('starts', i)
        job_list.append(pool.apply_async(fun_async, (xi_list[i],) ))
        if verbose: log(i, xi_list[i])

    res_list = []
    for i in range(len(job_list)):
        job_result = job_list[i].get()
        if job_result is not None:
            res_list.append(job_result)
        log(i, 'job finished')

    pool.close(); pool.join(); pool = None
    log('n_processed', len(res_list))
    return res_list



####  S3 --> Pandas ################################################################################
def pd_to_file_s3(df:pd.DataFrame, filei:str,  check=0, verbose=True, show='shape', db_name_aws=None, table_name_aws=None,   **kw):
  """function pd_to_file.
  Doc::
  """
  if "s3:" in filei:
     log(df)
     filei   = s3_path_norm(filei)
     session = aws_get_session()
     if ".parquet" in filei:
           wr.s3.to_parquet(df, path=filei, boto3_session= session,database= db_name_aws,    # Athena/Glue database
             table   = table_name_aws  # Athena/Glue table
           )
     elif ".csv" in filei:
           wr.s3.to_csv(df, path=filei, boto3_session= session,)   
     else :
           log('file unknown') 
     log(filei)
  else :
      pd_to_file(df, filei, check, verbose, show, **kw) 


def pd_read_file_s3(path_s3="s3://mybucket", suffix=None,npool=2, dataset=False,show=0, nrows=1000000000, session=None,
                    lower_level=0, upper_level=0,
     **kw)->pd.DataFrame:
    """  Read file in parallel from S3, Support high number of files.
    Doc::
            path (Union[str, List[str]]) – S3 prefix (accepts Unix shell-style wildcards) (e.g. s3://bucket/prefix) or list of S3 objects paths (e.g. [s3://bucket/key0, s3://bucket/key1]).
            path_suffix (Union[str, List[str], None]) – Suffix or List of suffixes to be read (e.g. [“.json”]). If None, will try to read all files. (default)
            path_ignore_suffix (Union[str, List[str], None]) – Suffix or List of suffixes for S3 keys to be ignored.(e.g. [“_SUCCESS”]). If None, will try to read all files. (default)
            version_id (Optional[Union[str, Dict[str, str]]]) – Version id of the object or mapping of object path to version id. (e.g. {‘s3://bucket/key0’: ‘121212’, ‘s3://bucket/key1’: ‘343434’})
            ignore_empty (bool) – Ignore files with 0 bytes.
            orient (str) – Same as Pandas: https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_json.html
            use_threads (Union[bool, int]) – True to enable concurrent requests, False to disable multiple threads. If enabled os.cpu_count() will be used as the max number of threads. If integer is provided, specified number is used.
            last_modified_begin – Filter the s3 files by the Last modified date of the object. The filter is applied only after list all s3 files.
            last_modified_end (datetime, optional) – Filter the s3 files by the Last modified date of the object. The filter is applied only after list all s3 files.
            boto3_session (boto3.Session(), optional) – Boto3 Session. The default boto3 session will be used if boto3_session receive None.
            s3_additional_kwargs (Optional[Dict[str, Any]]) – Forward to botocore requests, only “SSECustomerAlgorithm” and “SSECustomerKey” arguments will be considered.
            chunksize (int, optional) – If specified, return an generator where chunksize is the number of rows to include in each chunk.
            dataset (bool) – If True read a JSON dataset instead of simple file(s) loading all the related partitions as columns. If True, the lines=True will be assumed by default.
            partition_filter (Optional[Callable[[Dict[str, str]], bool]]) – Callback Function filters to apply on PARTITION columns (PUSH-DOWN filter). This function MUST receive a single argument (Dict[str, str]) where keys are partitions names and values are partitions values. Partitions values will be always strings extracted from S3. This function MUST return a bool, True to read the partition or False to ignore it. Ignored if dataset=False. E.g lambda x: True if x["year"] == "2020" and x["month"] == "1" else False https://aws-sdk-pandas.readthedocs.io/en/2.17.0/tutorials/023%20-%20Flexible%20Partitions%20Filter.html
            pandas_kwargs – KEYWORD arguments forwarded to pandas.read_json(). You can NOT pass pandas_kwargs explicit, just add valid Pandas arguments in the function call and awswrangler will accept it. e.g. wr.s3.read_json(‘s3://bucket/prefix/’, lines=True, keep_default_dates=True) https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_json.html
            Returns
            Pandas DataFrame or a Generator in case of chunksize != None.
            Return type
            Union[pandas.DataFrame, Generator[pandas.DataFrame, None, None]]
    """
    log2(path_s3)
    
    suffix = path_s3.split("/")[-1].split("*")[-1] if suffix is None else suffix

    if "s3:" in path_s3 :
        session = aws_get_session() if session is None else session
        path_s3 = s3_path_norm(path_s3)

        if ("*" in path_s3 or dataset is False) and "**" not in path_s3 :
            if "*" in path_s3 :
                 files   = glob_glob_s3(path_s3, session = session, lower_level=lower_level, upper_level=upper_level, )
            elif isinstance(path_s3, list):  files = path_s3
            else :                           files = [ path_s3]

            if len(files)< 1 :
                log(f'No file {path_s3}')
                return None

            suffix = files[0].split("/")[-1].split(".")[-1]
            if   "json" in suffix :    dfall= wr.s3.read_json(files,   use_thread=npool, boto3_session=session, **kw)
            elif "parquet" in suffix : dfall= wr.s3.read_parquet(files,use_threads=npool,boto3_session=session, **kw)
            elif "csv" in suffix :     dfall= wr.s3.read_csv(files,    use_threads=npool,boto3_session=session, **kw)
            else :
                log(f'Unknown suffix {suffix}')
                return None
        else : 
            if "json" in suffix :
                dfall= wr.s3.read_json(path_s3, path_suffix=suffix, use_thread=npool, dataset=dataset, boto3_session=session, **kw)

            elif "parquet" in suffix :
                dfall= wr.s3.read_parquet(path_s3, path_suffix=suffix, use_threads=npool, dataset=dataset, boto3_session=session, **kw)

            elif "csv" in suffix :
                dfall= wr.s3.read_csv(path_s3, path_suffix=suffix, use_threads=npool, dataset=dataset, boto3_session=session, **kw)

    else:
        from src.utils.utilmy_base import pd_read_file
        dfall  = pd_read_file(path_s3, npool=npool, nrows=nrows,  **kw)

    dfall =dfall.iloc[:nrows, :]
    if show>0: 
         log(dfall, "\n", dfall.columns)
    return dfall



def s3_pd_read_json(path_s3="s3://mybucket", suffix=".json",npool=2, dataset=True,  **kw)->pd.DataFrame:
    """  Read file in parallel from S3, Support high number of files.
    Doc::
            path (Union[str, List[str]]) – S3 prefix (accepts Unix shell-style wildcards) (e.g. s3://bucket/prefix) or list of S3 objects paths (e.g. [s3://bucket/key0, s3://bucket/key1]).
            path_suffix (Union[str, List[str], None]) – Suffix or List of suffixes to be read (e.g. [“.json”]). If None, will try to read all files. (default)
            path_ignore_suffix (Union[str, List[str], None]) – Suffix or List of suffixes for S3 keys to be ignored.(e.g. [“_SUCCESS”]). If None, will try to read all files. (default)
            version_id (Optional[Union[str, Dict[str, str]]]) – Version id of the object or mapping of object path to version id. (e.g. {‘s3://bucket/key0’: ‘121212’, ‘s3://bucket/key1’: ‘343434’})
            ignore_empty (bool) – Ignore files with 0 bytes.
            orient (str) – Same as Pandas: https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_json.html
            use_threads (Union[bool, int]) – True to enable concurrent requests, False to disable multiple threads. If enabled os.cpu_count() will be used as the max number of threads. If integer is provided, specified number is used.
            last_modified_begin – Filter the s3 files by the Last modified date of the object. The filter is applied only after list all s3 files.
            last_modified_end (datetime, optional) – Filter the s3 files by the Last modified date of the object. The filter is applied only after list all s3 files.
            boto3_session (boto3.Session(), optional) – Boto3 Session. The default boto3 session will be used if boto3_session receive None.
            s3_additional_kwargs (Optional[Dict[str, Any]]) – Forward to botocore requests, only “SSECustomerAlgorithm” and “SSECustomerKey” arguments will be considered.
            chunksize (int, optional) – If specified, return an generator where chunksize is the number of rows to include in each chunk.
            dataset (bool) – If True read a JSON dataset instead of simple file(s) loading all the related partitions as columns. If True, the lines=True will be assumed by default.
            partition_filter (Optional[Callable[[Dict[str, str]], bool]]) – Callback Function filters to apply on PARTITION columns (PUSH-DOWN filter). This function MUST receive a single argument (Dict[str, str]) where keys are partitions names and values are partitions values. Partitions values will be always strings extracted from S3. This function MUST return a bool, True to read the partition or False to ignore it. Ignored if dataset=False. E.g lambda x: True if x["year"] == "2020" and x["month"] == "1" else False https://aws-sdk-pandas.readthedocs.io/en/2.17.0/tutorials/023%20-%20Flexible%20Partitions%20Filter.html
            pandas_kwargs – KEYWORD arguments forwarded to pandas.read_json(). You can NOT pass pandas_kwargs explicit, just add valid Pandas arguments in the function call and awswrangler will accept it. e.g. wr.s3.read_json(‘s3://bucket/prefix/’, lines=True, keep_default_dates=True) https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_json.html
            Returns
            Pandas DataFrame or a Generator in case of chunksize != None.
            Return type
            Union[pandas.DataFrame, Generator[pandas.DataFrame, None, None]]
    """
    dfall         = wr.s3.read_json(path=path_s3, path_suffix=suffix, use_thread=npool, dataset=dataset, **kw)
    return dfall



def s3_pd_read_json2(path_s3="s3://mybucket", suffix=".json", ignore_index=True,  cols=None, verbose=False, nrows=-1, nfile=1000000, concat_sort=True, n_pool=1, npool=None,
                 drop_duplicates=None, col_filter:str=None,  col_filter_vals:list=None, dtype_reduce=None, fun_apply=None, use_ext=None,  **kw)->pd.DataFrame:
    """  Read file in parallel from disk, Support high number of files.
    Doc::
        path_s3: 
        return: pd.DataFrame
    """
    from smart_open import open
    def log(*s, **kw):
        print(*s, flush=True, **kw)

    n_pool = npool if isinstance(npool, int)  else n_pool ## alias

    ### Global Session, Shared across Threads
    session = boto3.Session()   
    client  = session.client('s3')

    file_list = s3_get_filelist(path_s3, suffix= suffix)
    n_file    = len(file_list)

    readers = { ".pkl"     : pd.read_pickle, ".parquet" : pd.read_parquet,
                ".tsv"     : pd.read_csv, ".csv"     : pd.read_csv, ".txt"     : pd.read_csv, ".zip"     : pd.read_csv,
                ".gzip"    : pd.read_csv, ".gz"      : pd.read_csv,
     }
     
    #### Pool count  ###############################################
    if n_pool < 1 :  n_pool = 1
    if n_file <= 0:  m_job  = 0
    elif n_file <= 2:
      m_job  = n_file
      n_pool = 1
    else  :
      m_job  = 1 + n_file // n_pool  if n_file >= 3 else 1
    if verbose : log(n_file,  n_file // n_pool )

    ### TODO : use with kewyword arguments
    pd_reader_obj2 = None

    #### Async Function ############################################
    def fun_async(filei):
        ext  = os.path.splitext(filei)[1]
        if ext is None or ext == '': ext ='.parquet'

        pd_reader_obj = readers.get(ext, None)
        try :
            with open(path_s3, mode='r', transport_params={'client': client} ) as f:
                # file_content = f.read()
                # dfi = pd_reader_obj(f)
                dfi = pd.read_json(f, lines=True) 

        except Exception as e :
          log(e)

        # if dtype_reduce is not None:    dfi = pd_dtype_reduce(dfi, int0 ='int32', float0 = 'float32')
        if col_filter is not None :       dfi = dfi[ dfi[col_filter].isin(col_filter_vals) ]
        if cols is not None :             dfi = dfi[cols]
        if nrows > 0        :             dfi = dfi.iloc[:nrows,:]
        if drop_duplicates is not None  : dfi = dfi.drop_duplicates(drop_duplicates)
        if fun_apply is not None  :       dfi = dfi.apply(lambda  x : fun_apply(x), axis=1)
        return dfi


    from multiprocessing.pool import ThreadPool
    pool   = ThreadPool(processes=n_pool)
    dfall  = pd.DataFrame(columns=cols) if cols is not None else pd.DataFrame()
    for j in range(0, m_job ) :
        if verbose : log("Pool", j, end=",")
        job_list = []
        for i in range(n_pool):
           if n_pool*j + i >= n_file  : break

           filei         = file_list[n_pool*j + i]
           job_list.append( pool.apply_async(fun_async, (filei, )))
           if verbose : log(j, filei)

        for i in range(n_pool):
            try :
                  if i >= len(job_list): break
                  dfi   = job_list[ i].get()
                  dfall = pd.concat( (dfall, dfi), ignore_index=ignore_index, sort= concat_sort)
                  #log("Len", n_pool*j + i, len(dfall))
                  del dfi; gc.collect()
            except Exception as e:
                log('error', filei, e)


    pool.close() ; pool.join() ;  pool = None
    if m_job>0 and verbose : log(n_file, j * n_file//n_pool )
    return dfall




#####################################################################################################
def s3_donwload(path_s3="", n_pool=5, dir_error=None, start_delay=0.1, verbose=True,   **kw):
    """  Run Multi-thread fun_async on input_list.
    Doc::
        # Define where to store artifacts:
        # - temporarily downloaded file and
        # - list of failed to download file in csv file
    """

    # Required library
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from functools import partial
    from smart_open import open


    def load_json(raw_json_data):
        with open(raw_json_data, mode='r') as f:
            data = json.loads(f)
        return data

    def s3_get_filelist(BUCKET):
        """
            Get all json files in a S3 bucket
        """
        s3 = boto3.resource('s3')

        my_bucket = s3.Bucket(BUCKET)
        s3_objects = []
        for file in my_bucket.objects.all():
            # filter only json files
            if file.key.lower().find(".json") != -1:
                s3_objects.append(file.key)
        return s3_objects

    def download_one_file(res_data: dict, bucket: str, client: boto3.client, s3_file: str):
        """ Download a single file from S3
        Args:
            res_data (dict): Store result of our json s3 reading
            bucket (str): S3 bucket where images are hosted
            output (str): Dir to store the images
            client (boto3.client): S3 client
            s3_file (str): S3 object name
        """
        bytes_buffer = io.BytesIO()
        client.download_fileobj(Bucket=bucket, Key=s3_file, Fileobj=bytes_buffer)
        byte_value = bytes_buffer.getvalue()
        res_data[s3_file] = byte_value.decode()


    files_to_download = s3_get_filelist(path_s3)
    # Creating only one session and one client
    session = boto3.Session()
    client = session.client("s3")
    
    res_data = {}

    ## The client is shared between threads
    func = partial(download_one_file, res_data, path_s3, client)


    ## List for storing possible failed downloads to retry later
    failed_downloads = []

    with ThreadPoolExecutor(max_workers=n_pool) as executor:
        # Using a dict for preserving the downloaded file for each future, to store it as a failure if we need that
        futures = {
            executor.submit(func, file_to_download): file_to_download for file_to_download in files_to_download
        }
        for future in as_completed(futures):
            if future.exception():
                failed_downloads.append(futures[future])

    if len(failed_downloads) > 0  and dir_error is not None :
       log(failed_downloads)

    return res_data
 


####################################################################################
def s3_get_filelist_cmd(parent_cmd: list) -> list:
    """ AWS CLI S3 Call by subprocess and get list of  results:
        list of (name, date, size)
    """
    import json
    from subprocess import PIPE, Popen

    files_list = []
    # Run the cmd that we were passed and store the output
    proc = Popen(parent_cmd, stdout=PIPE, stderr=PIPE)
    out, err = proc.communicate()

    # If the cmd exited without error code, continue
    if proc.returncode == 0:

        # Load the output as JSON and add the response to files_list
        output = json.loads(out.decode("utf8"))
        files_list.extend(output["Contents"])

        # If there is a valid NextToken make recursive calls until there isn't
        if output["NextToken"]:

            # Create a copy of parent cmd
            recursive_cmd = parent_cmd[:]

            # If there was a starting token in previous request remove it
            if "--starting-token" in recursive_cmd:
                recursive_cmd.pop(-1)
                recursive_cmd.pop(-1)

            # Add NextToken as starting-token to next cli cmd
            recursive_cmd.extend(["--starting-token", output["NextToken"]])

            # Run the cmd and add the result to files list
            files_list.extend(s3_get_filelist_cmd(recursive_cmd))
    else:
        log("Oh No. An Error Occurred!")
        raise Exception(err.decode("utf8"))

    # Return files_list which contains all data for this
    return files_list



def s3_split_path(s3_path)->Tuple[str,str]:
    """ path -->  bucket, key
    """
    path_parts=s3_path.replace("s3://","").split("/")
    bucket=path_parts.pop(0)
    key="/".join(path_parts)
    return bucket, key



def glob_s3_dirs(path:str, suffix:str="", start_date:str="", end_modified_date:str="" ):
    """ Glob for directory
    Docs:

        path (str) – S3 path (e.g. s3://bucket/prefix).
        suffix (Union[str, List[str], None]) – Suffix or List of suffixes for filtering S3 keys.
        ignore_suffix (Union[str, List[str], None]) – Suffix or List of suffixes for S3 keys to be ignored.
        last_modified_begin – Filter the s3 files by the Last modified date of the object. The filter is applied only after list all s3 files.
        last_modified_end (datetime, optional) – Filter the s3 files by the Last modified date of the object. The filter is applied only after list all s3 files.
        ignore_empty (bool) – Ignore files with 0 bytes.
        chunked (bool) – If True returns iterator, and a single list otherwise. False by default.
        s3_additional_kwargs (Optional[Dict[str, Any]]) – Forwarded to botocore requests. e.g. s3_additional_kwargs = {‘RequestPayer’: ‘requester’}
        boto3_session (boto3.Session(), optional) – Boto3 Session. The default boto3 session will be used if boto3_session receive None.

    Returns: List
    """
    session = aws_get_session()  
    flist_fullpath = wr.s3.list_directories(path, boto3_session= session )
    return  flist_fullpath


def glob_s3_files(path:str, suffix:str="", start_date:str="", end_modified_date:str="", session=None ):
    """ Glob for directory
    Docs:

        path (str) – S3 path (e.g. s3://bucket/prefix).
        suffix (Union[str, List[str], None]) – Suffix or List of suffixes for filtering S3 keys.
        ignore_suffix (Union[str, List[str], None]) – Suffix or List of suffixes for S3 keys to be ignored.
        last_modified_begin – Filter the s3 files by the Last modified date of the object. The filter is applied only after list all s3 files.
        last_modified_end (datetime, optional) – Filter the s3 files by the Last modified date of the object. The filter is applied only after list all s3 files.
        ignore_empty (bool) – Ignore files with 0 bytes.
        chunked (bool) – If True returns iterator, and a single list otherwise. False by default.
        s3_additional_kwargs (Optional[Dict[str, Any]]) – Forwarded to botocore requests. e.g. s3_additional_kwargs = {‘RequestPayer’: ‘requester’}
        boto3_session (boto3.Session(), optional) – Boto3 Session. The default boto3 session will be used if boto3_session receive None.

    Returns: List
    """
    session = aws_get_session()  if session is None else session
    path = s3_path_norm(path)
    flist_fullpath = wr.s3.list_objects(path, boto3_session= session )
    return  flist_fullpath


def glob_glob_s3(path:str, session=None, lower_level=0, upper_level=0, ):

   log(path)
   if "s3:" in path :
        flist= glob_s3_files(path, session=session)
   else :
        flist= glob_glob(path)

   root = []
   for pi in path.split("/"):
       if "*" in pi : break
       root.append(pi)
   root = "/".join(root) 

   #log(flist)
   #log(root)
   flist = glob_filter_dirlevel(flist,root=root, lower_level=lower_level, upper_level=upper_level )
   return flist


def glob_s3(path: str, recursive: bool = True,
            max_items_per_api_call: str = 1000,
            fields = "name,date,size",
            return_format='tuple',
            extra_params: list = None,
            folder_only=False) -> list:
    """  Glob files on S3 using AWS CLI
    Docs::
        path: str, recursive: bool = True,
        max_items_per_api_call: str = 1000,
        fields = "name,date,size"
        return_format='tuple'
        extra_params: list = None
        https://bobbyhadz.com/blog/aws-cli-list-all-files-in-bucket
    """        
    bucket_name, path = s3_split_path(path)

    #### {Name: Key, LastModified: LastModified, Size: Size}
    sfield= ""
    if 'name' in fields : sfield += "{Name: Key,"
    log(sfield)
    if 'date' in fields : sfield += "LastModified: LastModified,"
    if 'size' in fields : sfield += "Size: Size,"   
    sfield = sfield[:-1] + "}"
    log(sfield)

    ####  list-directories

    list_elt = "list-objects-v2"
    # Create cmd to list all objects with default pagination
    cmd = ["aws", "s3api", list_elt, "--bucket", bucket_name, "--output", "json",
            "--query", "{Contents: Contents[]." + sfield + "  ,NextToken: NextToken}"]

    log(cmd)

    # If pagination is not required, add flag
    if not recursive:
        cmd.append("--no-paginate")
    else:
        # Note : max_items_per_api_call * 1000 is the limit of files that this function can process
        cmd.extend(["--max-items", str(max_items_per_api_call)])

    # If only specific path is needed to be listed, add it
    if path:   cmd.extend(["--prefix", path])

    # If any extra params were passed, add them here
    if extra_params:   cmd.extend(extra_params)

    # run cmd and return files data
    files_data = s3_get_filelist_cmd(cmd)

    if 'tuple' in return_format:
      flist = []
      for xi in files_data :
        xlist = tuple()
        if xi.get("Name", None):          xlist += (xi['Name'],) 
        if xi.get("LastModified", None):  xlist += (xi['LastModified'],)
        if xi.get("Output", None):        xlist += (xi['Output'],)
        flist.append(xlist)

      return flist
    else :  
      return files_data


def s3_load_file(s3_path: str, 
                 extra_params: list = None, 
                 return_stream: bool = False, 
                 is_binary: bool = False) -> Union[str, IO, bytes]:
    """ Load file in memory using AWS CLI  --> subprocess --> stdout --> python
    Docs::
          file_data = get_data(s3_path="", extra_params=[])
          
          extra params:
          return_stream:  return as stream data
          is_binary :     return as binary string
          Infos:
             cmd = ["aws", "s3", "cp", s3_path, "-"]
             https://loige.co/aws-command-line-s3-content-from-stdin-or-to-stdout/
             https://aws.amazon.com/blogs/media/processing-user-generated-content-using-aws-lambda-and-ffmpeg/
             https://stackoverflow.com/questions/48725405/how-to-read-binary-data-over-a-pipe-from-another-process-in-python
    """             
    from subprocess import PIPE, Popen

    cmd = ["aws", "s3", "cp", s3_path, "-"]

    # If any extra params were passed, add them here
    if extra_params:   cmd.extend(extra_params)

    # Run cmd
    proc = Popen(cmd, stdout=PIPE, stderr=PIPE)

    # If we need a stream
    if return_stream: return proc.stdout


    # If we need to return the data only
    file_data = ""
    if not is_binary:
        for this_line in iter(proc.stdout.readline, b''):

            # Poll for return code
            proc.poll()
            # If return code exists exit from loop
            if proc.returncode is not None:
                break

            # Decode the binary stream
            this_line_decoded = this_line.decode("utf8")
            if this_line_decoded:
                # In case you want to have stdout as well
                # If removed there will be no indication that we are still receiving the data
                log(this_line_decoded)
                file_data = file_data + "\n" + this_line_decoded
    else:
        for this_bit in iter(proc.stdout.read, b''):
            file_data = bytes()
            log(this_bit, sep="", end="")
            file_data = file_data + this_bit

    # If the process returncode is None and we reach here, start polling for returncode until it exists
    while proc.returncode is None:
        proc.poll()

    # raise exception if error occurred, else return file_data
    if proc.returncode != 0 and proc.returncode is not None:
        _, err = proc.communicate()
        raise Exception(f"Error occurred with exit code {proc.returncode}\n{str(err.decode('utf8'))}")
    elif proc.returncode == 0:
        return file_data


def aws_log_fetch(dt_start, dt_end, logroup="", dirout='mylog.csv'):
   # Construct the AWS CLI command to start the query with specified parameters
   command = "aws logs start-query --log-group-name "+logroup+" --start-time "+dt_start+" --end-time "+dt_end+" --query-string \"fields @timestamp, @message | filter @logStream like 'my-log-stream' | fields time,log # , tomillis(@timestamp) as millis | filter log like 'CKS;' | limit 1000\""

   # Run the command in the shell and capture the output
   output = subprocess.check_output(command, shell=True)

   # Parse the JSON output to extract the query ID
   data = json.loads(output)
   query_id=data['queryId']

   # Construct the AWS CLI command to get the query results and save them to a file
   command = 'aws logs get-query-results --query-id "' + query_id + '" | jq -r \'.results[] | map(.value) | @csv\' > "' + dirout + '"'

   # Run the command in the shell to save the results to a file
   os.system(command)


############################################################################################################
if __name__ == '__main__':
    fire.Fire()
