#!/usr/bin/python
import os,re,string,sys, subprocess
from optparse import OptionParser

parser = OptionParser()
parser.add_option("-t", "--target", dest="target", help="rsync target")
parser.add_option("-m", "--max", dest="max", help="max number of bytes")
parser.add_option("-V", "--version", dest="versionarg", action="store_true", help="max number of bytes")

(options, args) = parser.parse_args()

if options.versionarg:
	print "1"
	sys.exit()

if not options.target and not options.max:
	print "We need -t and -m arguments, see --help"
	sys.exit("Need arguments")
	
options.max = int(options.max)

#Do a rsync dry run, doesn't download anything or touch the destination directory
#This works *ok* but sometimes it prints junk to the screen
#response = os.popen("rsync -a --stats --dry-run "+options.target+" foo").read()
#Subprocess is silent on *most* python instances so far
proc = subprocess.Popen("rsync -a --stats --dry-run "+options.target+" foo", stdout=subprocess.PIPE, shell=True)
(out, err) = proc.communicate()


filesize = re.findall('Total file size: ([^\n]+) bytes', out)

#Some versions of rsync add commas to the numbers
filesize = int(string.replace(filesize[0],",",""))

if options.max < filesize:
	sys.exit("Too big")
