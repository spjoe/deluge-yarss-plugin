#
# core.py
#
# Copyright (C) 2009 Camillo Dell'mour <cdellmour@gmail.com>
#
# Basic plugin template created by:
# Copyright (C) 2008 Martijn Voncken <mvoncken@gmail.com>
# Copyright (C) 2007-2009 Andrew Resch <andrewresch@gmail.com>
# Copyright (C) 2009 Damien Churchill <damoxc@gmail.com>
#
# Deluge is free software.
#
# You may redistribute it and/or modify it under the terms of the
# GNU General Public License, as published by the Free Software
# Foundation; either version 3 of the License, or (at your option)
# any later version.
#
# deluge is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with deluge.    If not, write to:
# 	The Free Software Foundation, Inc.,
# 	51 Franklin Street, Fifth Floor
# 	Boston, MA  02110-1301, USA.
#
#    In addition, as a special exception, the copyright holders give
#    permission to link the code of portions of this program with the OpenSSL
#    library.
#    You must obey the GNU General Public License in all respects for all of
#    the code used other than OpenSSL. If you modify file(s) with this
#    exception, you may extend this exception to your version of the file(s),
#    but you are not obligated to do so. If you do not wish to do so, delete
#    this exception statement from your version. If you delete this exception
#    statement from all source files in the program, then also delete it here.
#
from deluge._libtorrent import lt
from deluge.log import LOG as log
from deluge.plugins.pluginbase import CorePluginBase
import deluge.component as component
import deluge.configmanager
from deluge.core.rpcserver import export
import feedparser
import re
from twisted.internet.task import LoopingCall
import urllib
import datetime



DEFAULT_PREFS = {
    "updatetime":1800,
    "abos":{}
}

class Core(CorePluginBase):
    def enable(self):
        self.config = deluge.configmanager.ConfigManager("yarss.conf", DEFAULT_PREFS)
        self.update_status_timer = LoopingCall(self.update_handler)
        #self.update_handler()
        self.update_status_timer.start(self.config['updatetime'])

        
    def disable(self):
        self.update_status_timer.stop()
	self.config.save();

    def update(self):
        pass

    @export
    def set_config(self, config):
        "sets the config dictionary"
        for key in config.keys():
            self.config[key] = config[key]
        self.config.save()

    @export
    def get_config(self):
        "returns the config dictionary"
        return self.config.config

    def load_torrent(self, filename):
        try:
            log.debug("Attempting to open %s for add.", filename)
            _file = open(filename, "rb")
            filedump = _file.read()
            if not filedump:
                raise RuntimeError, "Torrent is 0 bytes!"
            _file.close()
        except IOError, e:
            log.warning("Unable to open %s: %s", filename, e)
            raise e

        # Get the info to see if any exceptions are raised
        info = lt.torrent_info(lt.bdecode(filedump))

        return filedump

    def add_torrent(self,url):
        log.debug("add torrent: %s", url)
        import tempfile
        import os.path
        tmp_file = os.path.join(tempfile.gettempdir(), url.split("/")[-1])

	def on_part(data, current_length, total_length):
            if total_length:
                percent = float(current_length) / float(total_length)
            else:
                pass

        def on_download_success(result):
            log.debug("Download success!")
            opts={}
            filedump = self.load_torrent(tmp_file)
	    torrent_id = component.get("TorrentManager").add(filedump=filedump, filename=tmp_file, options=opts)

        def on_download_fail(result):
            log.debug("Download failed: %s", result)
            

        import deluge.httpdownloader
        d = deluge.httpdownloader.download_file(url, tmp_file, on_part)
        d.addCallback(on_download_success)
        d.addErrback(on_download_fail)

    @export
    def add_eztv_abo(self,show,quality,name=None):
#    "format of config name = (distri,url,regex,show,quality,active,search())"
	url = "http://ezrss.it/search/index.php?show_name=%s&date=&quality=%s&quality_exact=true&release_group=&mode=rss" % (urllib.quote_plus(show), urllib.quote_plus(quality))
	log.debug("Url: %s added",url)
        if name is None:
            name = show
        date = datetime.datetime(datetime.MINYEAR,1,1,0,0,0,0).isoformat()
        self.config["abos"][name] = ("EZTV",url,"",show,quality,True,True,date)
	self.config.save()
    @export
    def add_feed(self,url,regex,name):
#    "format of config name = (distri,url,regex,show,quality,active,search())"
        date = datetime.datetime(datetime.MINYEAR,1,1,0,0,0,0).isoformat()
        self.config["abos"][name] = ("Custom",url,regex,"","",True,True,date)
	self.config.save()
    @export
    def remove_feed(self,name):
        del self.config["abos"][name]

    @export
    def refresh(self,updatetime = 0):
        #self.update_handler()
        self.update_status_timer.stop()
	if updatetime == 0:
            self.update_status_timer.start(self.config['updatetime'])
        else:
            self.update_status_timer.start(updatetime)
    @export
    def disable_feed(self,name):
        log.debug("disable_feed: %s", name)
        (dist,url,regex,show,quality,active,search,date) = self.config["abos"][name]
        self.config["abos"][name] = (dist,url,regex,show,quality,False,search,date)
    @export 
    def enable_feed(self,name):
        log.debug("enable_feed: %s", name)
        (dist,url,regex,show,quality,active,search,date) = self.config["abos"][name]
        self.config["abos"][name] = (dist,url,regex,show,quality,True,search,date)

    @export
    def edit_feed(self,name,feed):
        self.config["abos"][name] = feed

    def update_handler(self):
        log.debug("update handler executed")
        for key in self.config["abos"].keys():
            (dist,url,regex,show,quality,active,search,date) = self.config["abos"][key]
            if active == True:
                self.fetch_feed(url,regex,search,date,key)

    def fetch_feed(self,url,regex,search,date,name):
        log.debug('fetch_feed function')
        d = feedparser.parse(url)
        p = re.compile(regex)
	newdate = datetime.datetime.strptime(date,"%Y-%m-%dT%H:%M:%S")
        tmpdate = newdate
        for i in d['items']:
            if search == True:
                m = p.search(i['title'])
            else:
                m = p.match(i['title'])
            if m and newdate < datetime.datetime(*i.date_parsed[:6]):
                print i['link']
                self.add_torrent(i['link'])
        for i in d['items']:
            dt = datetime.datetime(*i.date_parsed[:6])
            if tmpdate < dt:
                tmpdate = dt
        (dist,url,regex,show,quality,active,search,date) = self.config["abos"][name]
        self.config["abos"][name] = (dist,url,regex,show,quality,active,search,tmpdate.isoformat())
