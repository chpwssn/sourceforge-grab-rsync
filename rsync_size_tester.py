#!/usr/bin/python
import os,re,string
from optparse import OptionParser

parser = OptionParser()
parser.add_option("-t", "--target", dest="target", help="rsync target")
parser.add_option("-m", "--max", dest="max", help="max number of bytes")

(options, args) = parser.parse_args()

if not options.target and not options.max:
	print "We need -t and -m arguments, see --help"
	
options.max = int(options.max)

#Do a rsync dry run, doesn't download anything or touch the destination directory
response = os.popen("rsync -a --stats --dry-run "+options.target+" foo").read()
filesize = re.findall('Total file size: ([^\n]+) bytes', response)

#Some versions of rsync add commas to the numbers
filesize = int(string.replace(filesize[0],",",""))

if options.max < filesize:
	print "Too big!"
	quit(2)
