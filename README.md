# About
This script iterates through all Ansible Collections which are available from the Ansible Automation
Hub (console.redhat.com) in both the validated content and the certified content and prints out those
collections which have been updated or released within the asked timespan (through --timedelta <days>).

It provides rudimentary options via a config.yml to only show updates on certain collections, repositories
and namespaces

# Get started
```
pip3 install -r requirements.txt
python3 automation_hub_check_collections_update.py --client-id <client_id> --timedelta 7
```

## Authentication

Red Hat deprecated basic authentication for `console.redhat.com` APIs. This script now uses a
[Hybrid Cloud Console service account](https://docs.redhat.com/en/documentation/red_hat_hybrid_cloud_console/1-latest/html/creating_and_managing_service_accounts/index).

Creating a service account is straight forward:

1. In [console.redhat.com](https://console.redhat.com), open **Settings → Service Accounts** and create a service account.
1. Copy the generated **Client ID** and **Client secret** (the secret is shown only once).
1. Add the service account to a **User Access** group with permissions for Automation Hub.
1. Run the script with `--client-id` and `--client-secret`, or set environment variables:

```
export REDHAT_CLIENT_ID='<client_id>'
export REDHAT_CLIENT_SECRET='<client_secret>'
python3 automation_hub_check_collections_update.py --timedelta 7
```

If `--client-secret` is omitted, the script prompts for it.

# Possible future plans
- Build it as an Ansible Module?!
- Run it in a container
- Zabbix integration to get notified about new collection updates in a timely manner
