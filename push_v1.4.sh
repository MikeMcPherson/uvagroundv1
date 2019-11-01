#!/bin/bash
set -x # echo on

if [[ $1 != "" ]]
then git commit -a -m "$1"
else git commit -a
fi
git push origin v1.4

