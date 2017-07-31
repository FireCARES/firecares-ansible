#!/bin/sh

# brew install jq
python hosts/ec2.py | jq '.|=with_entries(select(.key|test("tag_Name_web_server_prod")))'
