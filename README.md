# About
This script iterates through all Ansible Collections which are available from the Ansible Automation 
Hub (console.redhat.com) in both the validated content and the certified content and prints out those
collections which have been updated or released within the asked timespan (through --timedelta <days>).

It provides rudimentary options via a config.yml to only show updates on certain collections, repositories
and namespaces

# Get started
```
pip3 install -r requirements.txt
python3 automation_hub_check_collections_update.py <your commandline arguments here>
``` 

# Possible future plans
- Make use of environment variables as additional mean of retrieving values such as the API user and password; This is also
  as preperation for a version that runs in a container
- Build it as an Ansible Module?!
- Run it in a container
- Zabbix integration to get notified about new collection updates in a timely manner
