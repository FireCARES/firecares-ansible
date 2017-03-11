import sys
import json

j = json.load(sys.stdin)
include = j[sys.argv[1]]

# 1st arg = set to include
# if 2nd arg = filter out these from the set into include before generating the inventory

if len(sys.argv) == 3:
    res = ','.join(set(include) - set(j[sys.argv[2]]))
    print res + ',' if res else ''
else:
    res = ','.join(include)
    print res + ',' if res else ''
