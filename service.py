import xbmcplugin,xbmcaddon
import time
import datetime
import xbmc
import os
import urllib2,json
import zipfile
import resources.lib.utils as utils
from resources.lib.croniter import croniter
from collections import namedtuple
from shutil import copyfile

__addon__ = xbmcaddon.Addon()
__author__ = __addon__.getAddonInfo('author')
__scriptid__ = __addon__.getAddonInfo('id')
__scriptname__ = __addon__.getAddonInfo('name')
__cwd__ = __addon__.getAddonInfo('path')
__version__ = __addon__.getAddonInfo('version')
__language__ = __addon__.getLocalizedString
debug = __addon__.getSetting("debug")
offset1hr = __addon__.getSetting("offset1hr")

class epgUpdater:
    def __init__(self):
        self.monitor = UpdateMonitor(update_method = self.settingsChanged)
        self.enabled = utils.getSetting("enable_scheduler")
        self.next_run = 0
        self.update_m3u = False

        try:
          self.rocketstreams_addon = xbmcaddon.Addon('plugin.video.rocketstreams')
        except:
          utils.log("Failed to find rocketstreams addon")
          self.rocketstreams_addon = None
        try:
          self.pvriptvsimple_addon = xbmcaddon.Addon('pvr.iptvsimple')
        except:
          utils.log("Failed to find pvr.iptvsimple addon")
          self.pvriptvsimple_addon = None

    def run(self):
        utils.log("StalkerSettings::scheduler enabled, finding next run time")

        # Update when starting
        self.updateGroups()
        self.updateM3u()
        if self.enabled:
          self.updateEpg()

        self.findNextRun(time.time())
        while(not xbmc.abortRequested):
            # Sleep/wait for abort for 10 seconds
            now = time.time()
            if(self.enabled):
              if(self.next_run <= now):
                  self.updateEpg()
                  self.findNextRun(now)
              else:
                  self.findNextRun(now)
              if(self.update_m3u):
                  self.updateM3u()
                  self.update_m3u = False
            xbmc.sleep(500)
        # del self.monitor

    def updateGroups(self):
      self.groups = []
      for group in [ "USA", "CAN", "UK", "SPORTS", "FOR ADULTS", "PUNJABI", "PAKISTANI", "HINDI", "KIDS", "MALAYALAM", "TELUGU", "BRASIL", "MARATHI", "GUJARATI", "SERBIA", "SPANISH", "ARABIC", "FILIPINO", "BANGLA", "SINHALA", "CRICKET", "AFGHANISTAN", "KANNADA", "TAMIL", "NEPALI", "AFRICAN", "ITALY", "CARRIBEAN", "GREECE", "ROMANIAN", "CZ&SLOVAK", "MOVIE CH/HBO PPV", "POLISH", "PORTUGUESE", "NFL", "RUSSIA/UKRAINE", "TEST"]:
        if utils.getSetting(group) == 'true':
          self.groups.append(group)

    def installKeyboardFile(self):
      keyboard_file_path = os.path.join(xbmc.translatePath('special://home'), 'addons/service.rocketstreamsEpgUpdate/keyboard.xml')
      if os.path.isfile(keyboard_file_path):
        utils.log("Keyboard file found.  Copying...")
        copyfile(keyboard_file_path, os.path.join(xbmc.translatePath('special://userdata'), 'keymaps/keyboard.xml'))

    def settingsChanged(self):
        utils.log("Settings changed - update")
        utils.refreshAddon()
        current_enabled = utils.getSetting("enable_scheduler")
        install_keyboard_file = utils.getSetting("install_keyboard_file")
        if install_keyboard_file == 'true':
          self.installKeyboardFile()
          utils.setSetting('install_keyboard_file', 'false')
          # Return since this is going to be run immediately again
          return
        
        # Update m3u file if wanted groups has changed
        old_groups = self.groups
        self.updateGroups()
        if self.groups != old_groups:
          self.update_m3u = True

        if(self.enabled == "true"):
            #always recheck the next run time after an update
            utils.log('recalculate start time , after settings update')
            self.findNextRun(time.time())

    def parseSchedule(self):
        schedule_type = int(utils.getSetting("schedule_interval"))
        cron_exp = utils.getSetting("cron_schedule")

        hour_of_day = utils.getSetting("schedule_time")
        hour_of_day = int(hour_of_day[0:2])
        if(schedule_type == 0 or schedule_type == 1):
            #every day
            cron_exp = "0 " + str(hour_of_day) + " * * *"
        elif(schedule_type == 2):
            #once a week
            day_of_week = utils.getSetting("day_of_week")
            cron_exp = "0 " + str(hour_of_day) + " * * " + day_of_week
        elif(schedule_type == 3):
            #first day of month
            cron_exp = "0 " + str(hour_of_day) + " 1 * *"

        return cron_exp


    def findNextRun(self,now):
        #find the cron expression and get the next run time
        cron_exp = self.parseSchedule()
        cron_ob = croniter(cron_exp,datetime.datetime.fromtimestamp(now))
        new_run_time = cron_ob.get_next(float)
        # utils.log('new run time' +  str(new_run_time))
        # utils.log('next run time' + str(self.next_run))
        if(new_run_time != self.next_run):
            self.next_run = new_run_time
            utils.showNotification('EPG Updater', 'Next Update: ' + datetime.datetime.fromtimestamp(self.next_run).strftime('%m-%d-%Y %H:%M'))
            utils.log("scheduler will run again on " + datetime.datetime.fromtimestamp(self.next_run).strftime('%m-%d-%Y %H:%M'))


    def updateM3u(self):
        if self.rocketstreams_addon is None:
            utils.log("rocketstreams addon missing")
            return
        if self.pvriptvsimple_addon is None:
            utils.log("pvriptvsimple addon missing")
            return

        utils.log("Updating m3u file")
        username = self.rocketstreams_addon.getSetting('kasutajanimi')
        password = self.rocketstreams_addon.getSetting('salasona')
        updater_path = os.path.join(xbmc.translatePath('special://userdata'), 'addon_data/plugin.video.rocketstreams')

        cm_path = os.path.join(xbmc.translatePath('special://home'), 'addons/service.rocketstreamsEpgUpdate/channel_guide_map.txt')

        channel_map = {}
        if os.path.isfile(cm_path):
          utils.log('Adding mapped guide ids')
          with open(cm_path) as f:
            for line in f:
              channel_name,guide_id = line.rstrip().split("\t")
              channel_map[channel_name] = guide_id

        panel_url = "http://stream-two.doc123.nl:8000/panel_api.php?username={0}&password={1}".format(username, password)
        u = urllib2.urlopen(panel_url)
        j = json.loads(u.read())

        if j['user_info']['auth'] == 0:
          utils.showNotification("EPG Updater", "Error: Couldn't login to rocketstreams")
          self.enabled = False
          utils.setSetting("enable_scheduler", "False")
          return

        Channel = namedtuple('Channel', ['tvg_id', 'tvg_name', 'tvg_logo', 'group_title', 'channel_url'])
        channels = []

        group_idx = {}
        for idx,group in enumerate(self.groups):
          group_idx[group] = idx

        for ts_id, info in j["available_channels"].iteritems():
            channel_url = "http://stream-two.doc123.nl:8000/live/{0}/{1}/{2}.ts".format(username, password, ts_id)
            tvg_id = "" 
            tvg_name = info['name']
            if tvg_name.endswith(' - NEW'):
              tvg_name = tvg_name[:-6]
            #if info['epg_channel_id'] and info['epg_channel_id'].endswith(".com"):
            #    tvg_id = info['epg_channel_id']
            if tvg_name in channel_map:
                tvg_id = 'tvg-id="{0}"'.format(channel_map[tvg_name])
            else:
                tvg_id = ""
            tvg_id = ""
            tvg_logo = ""
            #if info['stream_icon']:
            #  tvg_logo = info['stream_icon']
            group_title = info['category_name']
            if group_title == None:
                group_title = 'None'
            channels.append(Channel(tvg_id, tvg_name, tvg_logo, group_title, channel_url))

        wanted_channels = [c for c in channels if c.group_title in self.groups]
        wanted_channels.sort(key=lambda c: "{0}-{1}".format(group_idx[c.group_title], c.tvg_name))

        with open("{0}/rocketstreams.m3u".format(updater_path), "w") as m3u_f:
            m3u_f.write("#EXTM3U\n")
            for c in wanted_channels:
                m3u_f.write('#EXTINF:-1 tvg-name="{0}" {1} tvg-logo="{2}" group-title="{3}",{0}\n{4}\n'.format(c.tvg_name, c.tvg_id, c.tvg_logo, c.group_title, c.channel_url))

        self.checkAndUpdatePVRIPTVSetting("epgCache", "false")
        self.checkAndUpdatePVRIPTVSetting("epgPathType", "0")
        self.checkAndUpdatePVRIPTVSetting("epgPath", updater_path + '/rocketstreams_xmltv.xml.gz')
        self.checkAndUpdatePVRIPTVSetting("m3uPathType", "0")
        self.checkAndUpdatePVRIPTVSetting("m3uPath", "{0}/rocketstreams.m3u".format(updater_path))

    def checkAndUpdatePVRIPTVSetting(self, setting, value):
      if self.pvriptvsimple_addon.getSetting(setting) != value:
        self.pvriptvsimple_addon.setSetting(setting, value)

    def updateEpg(self):
        epgFileName = 'merged.xml.gz'
        epgFile = None
        updater_path = os.path.join(xbmc.translatePath('special://userdata'), 'addon_data/plugin.video.rocketstreams')

        if self.rocketstreams_addon != None:
            try:
                response = urllib2.urlopen('http://rstreams.epg.ninja/epg.xml')
                epgFile = response.read()
            except:
                utils.log('StalkerSettings: Some issue with epg file')
                pass

            if epgFile:
                epgFH = open(updater_path + '/rocketstreams_xmltv.xml.gz', "wb")
                epgFH.write(epgFile)
                epgFH.close()

class UpdateMonitor(xbmc.Monitor):
    update_method = None

    def __init__(self,*args, **kwargs):
        xbmc.Monitor.__init__(self)
        self.update_method = kwargs['update_method']

    def onSettingsChanged(self):
        self.update_method()

if __name__ == "__main__":
  epg_updater = epgUpdater()
  epg_updater.run()
