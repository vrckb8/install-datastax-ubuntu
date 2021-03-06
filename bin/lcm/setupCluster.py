#!/usr/bin/python
import json
import argparse
import os
import utilLCM as lcm

def setupArgs():
    parser = argparse.ArgumentParser(description='Setup LCM managed DSE cluster, repo, config, and ssh creds',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    required = parser.add_argument_group('Required named arguments')
    required.add_argument('--clustername', required=True, type=str,
                          help='Name of cluster.')
    required.add_argument('--username', required=True, type=str,
                          help='username LCM uses when ssh-ing to nodes for install/config')
    required.add_argument('--repouser', required=True, type=str, help='username for DSE repo')
    required.add_argument('--repopw', required=True, type=str, help='pw for repouser')
    parser.add_argument('--opsc-ip', type=str, default='127.0.0.1',
                          help='IP of OpsCenter instance (or FQDN)')
    parser.add_argument('--opscuser', type=str, default='admin', help='opscenter admin user')
    parser.add_argument('--opscpw', type=str, default='admin', help='password for opscuser')
    parser.add_argument('--privkey', type=str,
                        help='abs path to private key (public key on all nodes) to be used by OpsCenter; --password OR --privkey required')
    parser.add_argument('--password', type=str,
                        help='password for username LCM uses when ssh-ing to nodes for install/config; --password OR --privkey required; IGNORED if privkey non-null.')
    parser.add_argument('--dsever', type=str, default="5.1.5",
                        help='DSE version for LCM config profile')
    parser.add_argument('--datapath', type=str, default=None,
                        help='path to root data directory containing data | commitlog | saved_caches (eg /data/cassandra); package default if not passed')
    parser.add_argument('--pause', type=int, default=6,
                        help="pause time (sec) between attempts to contact OpsCenter")
    parser.add_argument('--trys', type=int, default=100,
                        help="number of times to attempt to contact OpsCenter")
    parser.add_argument('--verbose', action='store_true', help='verbose flag, right now a NO-OP')
    return parser

def checkArgs(args):
    if args.password is None and args.privkey is None:
        print "setupCluster.py: error: argument --password OR --privkey is required"
        print "Run setupCluster.py -h for help message"
        exit(1)
    #Todo add key exists check

def main():
    parser = setupArgs()
    args = parser.parse_args()
    checkArgs(args)

    # Basic repo config
    dserepo = json.dumps({
        "name":"DSE repo",
        "username":args.repouser,
        "password":args.repopw})

    # If privkey passed read key content...
    if args.privkey != None:
        keypath = os.path.abspath(args.privkey)
        with open(keypath, 'r') as keyfile:
            privkey = keyfile.read()
        print "Will create cluster {c} on {u} with keypath {k}".format(c=args.clustername, u=args.opsc_ip, k=keypath)
        dsecred = json.dumps({
            "become-mode":"sudo",
            "use-ssh-keys":True,
            "name":"DSE creds",
            "login-user":args.username,
            "ssh-private-key":privkey,
            "become-user":None})
    # ...otherwise use a pw
    else:
        print "Will create cluster {c} on {u} with password".format(c=args.clustername, u=args.opsc_ip)
        dsecred = json.dumps({
            "become-mode":"sudo",
            "use-ssh-keys":False,
            "name":"DSE creds",
            "login-user":args.username,
            "login-password":args.password,
            "become-user":None})

    # Minimal config profile
    # Todo, read config json from a file
    defaultconfig = {
        "name":"Default config",
        "datastax-version": args.dsever,
        "json": {
            'cassandra-yaml': {
                "authenticator":"com.datastax.bdp.cassandra.auth.DseAuthenticator",
                "num_tokens":32,
                "endpoint_snitch":"GossipingPropertyFileSnitch"
            },
            "dse-yaml": {
                "authorization_options": {"enabled": True},
                "authentication_options": {"enabled": True}
            }
        }}
    # Since this isn't necessarily being called on the nodes where 'datapath'
    # exists checking is pointless
    if args.datapath != None:
        defaultconfig["json"]["cassandra-yaml"]["data_file_directories"] = [os.path.join(args.datapath, "data")]
        defaultconfig["json"]["cassandra-yaml"]["saved_caches_directory"] = os.path.join(args.datapath, "saved_caches")
        defaultconfig["json"]["cassandra-yaml"]["commitlog_directory"] = os.path.join(args.datapath, "commitlog")

    defaultconfig = json.dumps(defaultconfig)

    opsc = lcm.OpsCenter(args.opsc_ip, args.opscuser, args.opscpw)
    # Block waiting for OpsC to spin up, create session & login if needed
    opsc.setupSession(pause=args.pause, trys=args.trys)

    # Return config instead of bool?
    # This check is here to allow calling script from node instances if desired.
    # Ie script may be called multiple times.
    # Cluster doesn't esist -> must be 1st node -> do setup
    c = opsc.checkForCluster(args.clustername)
    if not c:
        print "Cluster {n} doesn't exist, creating...".format(n=args.clustername)
        cred = opsc.addCred(dsecred)
        repo = opsc.addRepo(dserepo)
        conf = opsc.addConfig(defaultconfig)
        cid = opsc.addCluster(args.clustername, cred['id'], repo['id'], conf['id'])
    else:
        print "Cluster {n} exists, exiting...".format(n=args.clustername)



# ----------------------------
if __name__ == "__main__":
    main()
