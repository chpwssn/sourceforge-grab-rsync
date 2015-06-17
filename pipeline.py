# encoding=utf8
import datetime
from distutils.version import StrictVersion
import hashlib
import os.path
import shutil
import socket
import sys
import time
import random
import string

import seesaw
from seesaw.config import NumberConfigValue
from seesaw.externalprocess import ExternalProcess
from seesaw.item import ItemInterpolation, ItemValue
from seesaw.pipeline import Pipeline
from seesaw.project import Project
from seesaw.task import SimpleTask, LimitConcurrent
from seesaw.tracker import GetItemFromTracker, PrepareStatsForTracker, \
	UploadWithTracker, SendDoneToTracker
from seesaw.util import find_executable




# check the seesaw version
if StrictVersion(seesaw.__version__) < StrictVersion("0.1.5"):
	raise Exception("This pipeline needs seesaw version 0.1.5 or higher.")


###########################################################################
# Find a useful rsync_size_tester executable.
#
RSYNC_TEST = find_executable(
	"rsync_size_tester",
	["1"],
	[
		"./rsync_size_tester.py",
		"../rsync_size_tester.py",
		"../../rsync_size_tester.py",
		"/home/warrior/rsync_size_tester.py",
		"/usr/bin/rsync_size_tester.py"
	]
)

#Yes this is hackish but run-pipeline won't let you add more command line args
#If the file "LARGE-RSYNC" is in the directory, allow larger rsync's
#Using Gigabytes not Gibibytes to be safe
if os.path.isfile("LARGE-RSYNC"):
	MAX_RSYNC = "150000000000"
else:
	MAX_RSYNC = "25000000000"


###########################################################################
# The version number of this pipeline definition.
#
# Update this each time you make a non-cosmetic change.
# It will be added to the WARC files and reported to the tracker.
VERSION = "20150617.06"
USER_AGENT = 'ArchiveTeam'
TRACKER_ID = 'sourceforgersync'
TRACKER_HOST = 'tracker.archiveteam.org'


###########################################################################
# This section defines project-specific tasks.
#
# Simple tasks (tasks that do not need any concurrency) are based on the
# SimpleTask class and have a process(item) method that is called for
# each item.
class CheckIP(SimpleTask):
	def __init__(self):
		SimpleTask.__init__(self, "CheckIP")
		self._counter = 0

	def process(self, item):
		# NEW for 2014! Check if we are behind firewall/proxy

		if self._counter <= 0:
			item.log_output('Checking IP address.')
			ip_set = set()

			ip_set.add(socket.gethostbyname('twitter.com'))
			ip_set.add(socket.gethostbyname('facebook.com'))
			ip_set.add(socket.gethostbyname('youtube.com'))
			ip_set.add(socket.gethostbyname('microsoft.com'))
			ip_set.add(socket.gethostbyname('icanhas.cheezburger.com'))
			ip_set.add(socket.gethostbyname('archiveteam.org'))

			if len(ip_set) != 6:
				item.log_output('Got IP addresses: {0}'.format(ip_set))
				item.log_output(
					'Are you behind a firewall/proxy? That is a big no-no!')
				raise Exception(
					'Are you behind a firewall/proxy? That is a big no-no!')

		# Check only occasionally
		if self._counter <= 0:
			self._counter = 10
		else:
			self._counter -= 1


class PrepareDirectories(SimpleTask):
	def __init__(self, warc_prefix):
		SimpleTask.__init__(self, "PrepareDirectories")
		self.warc_prefix = warc_prefix

	def process(self, item):
		item_name = item["item_name"]
		dirname = "/".join((item["data_dir"], item_name))

		if os.path.isdir(dirname):
			shutil.rmtree(dirname)

		os.makedirs(dirname)

		item["item_dir"] = dirname
		item["warc_file_base"] = "%s-%s-%s" % (self.warc_prefix,
											   item_name.replace(':', '_'),
											   time.strftime("%Y%m%d-%H%M%S"))

		open("%(item_dir)s/%(warc_file_base)s.warc.gz" % item, "w").close()

		
class getRsyncURL(object):
	def __init__(self,default_target):
		#SimpleTask.__init__(self, "GetRsyncURL")
		self.target = default_target
		
	def realize(self, item):
		#item.log_output(item['item_name'])
		item_type, item_project, item_mountpoint = item['item_name'].split(':')
		if item_type == "git":
			self.target = "git.code.sf.net::p/%(project)s/%(mountpoint)s.git" % {"project":item_project, "mountpoint":item_mountpoint}
		elif item_type == "svn":
			self.target = "svn.code.sf.net::p/%(project)s/%(mountpoint)s" % {"project":item_project, "mountpoint":item_mountpoint}
		elif item_type == "hg":
			self.target = "hg.code.sf.net::p/%(project)s/%(mountpoint)s" % {"project":item_project, "mountpoint":item_mountpoint}
		elif item_type == "cvs":
			self.target = "rsync://%(project)s.cvs.sourceforge.net/cvsroot/%(project)s/*" % {"project":item_project, "mountpoint":item_mountpoint}
		elif item_type == "bzr":
			self.target = "%(project)s.bzr.sourceforge.net::bzrroot/%(mountpoint)s/*" % {"project":item_project, "mountpoint":item_mountpoint}
		item.log_output(self.target)
		return self.target
	
		
	def __str__(self):
		return self.target
		
class outputName(object):
	def __init__(self):
		pass
		
	def realize(self, item):
		#item.log_output(item['item_name'])
		item_type, item_project, item_mountpoint = item['item_name'].split(':')
		return "%(project)s-%(SCM)s-%(mountpoint)s" % {"project":item_project, "SCM":item_type, "mountpoint":item_mountpoint}
		
class cleanItem(object):
	'''Removes the : in an item while formatting based on ItemInterpolation'''
	def __init__(self, s):
		self.s = s

	def realize(self, item):
		return string.replace(self.s % item,":",".")

	def __str__(self):
		return "<'" + string.replace(self.s % item,":",".") + "'>"


class MoveFiles(SimpleTask):
	def __init__(self):
		SimpleTask.__init__(self, "MoveFiles")

	def process(self, item):
		os.rename("%(item_dir)s/%(warc_file_base)s.txt.gz" % item,
				  "%(data_dir)s/%(warc_file_base)s.txt.gz" % item)

		shutil.rmtree("%(item_dir)s" % item)


def get_hash(filename):
	with open(filename, 'rb') as in_file:
		return hashlib.sha1(in_file.read()).hexdigest()


CWD = os.getcwd()
PIPELINE_SHA1 = get_hash(os.path.join(CWD, 'pipeline.py'))


def stats_id_function(item):
	# NEW for 2014! Some accountability hashes and stats.
	d = {
		'pipeline_hash': PIPELINE_SHA1,
		'python_version': sys.version,
	}

	return d


###########################################################################
# Initialize the project.
#
# This will be shown in the warrior management panel. The logo should not
# be too big. The deadline is optional.
project = Project(
	title="sourceforgersync",
	project_html="""
		<img class="project-logo" alt="Project logo" src="" height="50px" title=""/>
		<h2>sourceforge.net <span class="links"><a href="http://sourceforge.net/">Website</a> &middot; <a href="http://tracker.archiveteam.org/sourceforge/">Leaderboard</a></span></h2>
		<p>Saving all project from SourceForge. rsyncing all of the source code repositories.</p>
	"""
)

pipeline = Pipeline(
	CheckIP(),
	GetItemFromTracker("http://%s/%s" % (TRACKER_HOST, TRACKER_ID), downloader, VERSION),
	ExternalProcess("Size Test",[RSYNC_TEST,"-t",getRsyncURL("foo"),"-m",MAX_RSYNC]),
	LimitConcurrent(1,ExternalProcess("rsync", ["rsync", "-av", getRsyncURL("foo"), cleanItem("%(data_dir)s/%(item_name)s")])),
	ExternalProcess("tar", ["tar", "-czf", cleanItem("%(data_dir)s/%(item_name)s.tar.gz"), "-C", ItemInterpolation("%(data_dir)s/"), "--owner=1999", "--group=2015", "--no-same-permissions", cleanItem("%(item_name)s")]),
	LimitConcurrent(NumberConfigValue(min=1, max=4, default="1",
		name="shared:rsync_threads", title="Rsync threads",
		description="The maximum number of concurrent uploads."),
		UploadWithTracker(
			"http://%s/%s" % (TRACKER_HOST, TRACKER_ID),
			downloader=downloader,
			version=VERSION,
			files=[
				cleanItem("%(data_dir)s/%(item_name)s.tar.gz")
				#ItemInterpolation("foo.tar.gz")
			],
			rsync_target_source_path=ItemInterpolation("%(data_dir)s/"),
			rsync_extra_args=[
				"--recursive",
				"--partial",
				"--partial-dir", ".rsync-tmp",
			]
		),
	),
	PrepareStatsForTracker(
		defaults={"downloader": downloader, "version": VERSION},
		file_groups={
			"data": [
				cleanItem("%(data_dir)s/%(item_name)s.tar.gz")
			]
		},
		id_function=stats_id_function,
	),
	SendDoneToTracker(
		tracker_url="http://%s/%s" % (TRACKER_HOST, TRACKER_ID),
		stats=ItemValue("stats")
	)
)
