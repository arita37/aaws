# aaws

### install
```bash
git clone https://github.com/arita37/aaws.git   

cd aaws
git checkout dev
pip install reqs.txt

### in your bashrc
alias aaws="python  yourpath/aaws/utily_aws.py "


```



### Usage
```bash
aaws  test1


#### CloudWatch log fetch

## example 1
aaws  aws_logfetch --dtstart 20230414-1200  --dtend 20230414-1500 --logroup mygroup  --logstream mystream




### example 2
export aws_logroup=mygroup
export aws_logstream=mystream        
export aws_logqueries_file=myqueries.json               

### setup this file with pre-defined cloudwatch queries
  myqueries.json
  {
      "query1" :  "fields @timestamp, @message | filter @logStream like '{logstream}' | fields time,log # , tomillis(@timestamp) as millis | filter log like 'CKS;' | limit {nmax} "

      ,"query2" :  "fields @timestamp, @message | filter @logStream like '{logstream}' | fields time,log # , tomillis(@timestamp) as millis | filter log like 'CKS;' | limit {nmax} "

  }


aaws  aws_logfetch  --add_hours_start -5     ## from -5hours to now





```
