from rf_inventory import get_host_variables
# Don't touch this host, it's evil.

# This host is for 6.2.x Automated Regression setup.  See Katie

variables = {'name': 'areglinfshost-62r',
             'ip': '172.27.4.194',
             'ssh_user': 'root',
             'ssh_pass': '12!pass345',
             'ssh_private_key_file': '',
             'app': '/oob',
             'apps': ['/oob', '/cgvol1', '/cgvol2'],
             'app_list': ['/', '/boot', '/oob', '/cgvol1', '/cgvol2'],
             'app_exclude': ['/', '/boot'],
             }


def get_variables(prepend=None, append=None, delimiter='.', base=variables, **kwargs):
    return get_host_variables(base=base, prepend=prepend, append=append, delimiter=delimiter, **kwargs)

if __name__ == '__main__':
    print(get_variables('pre', 'app', 'delim'))
