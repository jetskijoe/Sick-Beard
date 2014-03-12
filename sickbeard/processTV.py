# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement

import os
import shutil
import time

import sickbeard 
from sickbeard import common
from sickbeard import postProcessor
from sickbeard import db, helpers, exceptions

from sickbeard import encodingKludge as ek
from sickbeard.exceptions import ex

from sickbeard import logger

from sickbeard import failedProcessor


def delete_folder(folder, check_empty=True):

    # check if it's a folder
    if not ek.ek(os.path.isdir, folder):
        return False

    # check if it isn't TV_DOWNLOAD_DIR
    if sickbeard.TV_DOWNLOAD_DIR:
        if helpers.real_path(folder) == helpers.real_path(sickbeard.TV_DOWNLOAD_DIR):
            return False

    # check if it's empty folder when wanted checked
    if check_empty:
        check_files = ek.ek(os.listdir, folder)
        if check_files:
            return False

    # try deleting folder
    try:
        logger.log(u"Deleting folder: " + folder)
        shutil.rmtree(folder)
    except (OSError, IOError), e:
        logger.log(u"Warning: unable to delete folder: " + folder + ": " + ex(e), logger.WARNING)
        return False

    return True
def logHelper (logMessage, logLevel=logger.MESSAGE):
    logger.log(logMessage, logLevel)
    return logMessage + u"\n"

def processDir(dirName, nzbName=None, method=None, recurse=False, pp_options={}, failed=False):
    """
    Scans through the files in dirName and processes whatever media files it finds
    dirName: The folder name to look in
    nzbName: The NZB name which resulted in this folder being downloaded
    method:  The method of postprocessing: Automatic, Script, Manual
    recurse: Boolean for whether we should descend into subfolders or not
    failed: Boolean for whether or not the download failed
    """
    returnStr = ''
    returnStr += logHelper(u"Processing folder: " + dirName, logger.DEBUG)
    if ek.ek(os.path.isdir, dirName):
        dirName = ek.ek(os.path.realpath, dirName)
    elif sickbeard.TV_DOWNLOAD_DIR and ek.ek(os.path.isdir, sickbeard.TV_DOWNLOAD_DIR) \
            and ek.ek(os.path.normpath, dirName) != ek.ek(os.path.normpath, sickbeard.TV_DOWNLOAD_DIR):
        dirName = ek.ek(os.path.join, sickbeard.TV_DOWNLOAD_DIR, ek.ek(os.path.abspath, dirName).split(os.path.sep)[-1])
        returnStr += logHelper(u"Trying to use folder: " + dirName, logger.DEBUG)
    if not ek.ek(os.path.isdir, dirName):
        returnStr += logHelper(u"Unable to figure out what folder to process. If your downloader and Sick Beard aren't on the same PC make sure you fill out your TV download dir in the config.", logger.DEBUG)
    	failed = True
        if failed:
            returnStr += _processFailed(dirName, nzbName)
    if ek.ek(os.path.basename, dirName).startswith('_FAILED_'):
        returnStr += logHelper(u"The directory name indicates it failed to extract, cancelling", logger.DEBUG)
        failed = True
        if failed:
            returnStr += _processFailed(dirName, nzbName)
    basename = ek.ek(os.path.basename, dirName)
    if basename.startswith("_UNDERSIZE_") or basename.startswith("_UNPACK_"):
        returnStr += logHelper(u"The directory name indicates failure. Treating this download as failed.", logger.DEBUG)
        failed = True
    if failed:
        returnStr += _processFailed(dirName, nzbName)
    else:
        myDB = db.DBConnection()
        sqlResults = myDB.select("SELECT * FROM tv_shows")
        for sqlShow in sqlResults:
            if dirName.lower().startswith(ek.ek(os.path.realpath, sqlShow["location"]).lower() + os.sep) or dirName.lower() == ek.ek(os.path.realpath, sqlShow["location"]).lower():
                returnStr += logHelper(u"You're trying to post process an episode that's already been moved to its show dir", logger.ERROR)
                return returnStr

        returnStr += _processNormal(dirName, nzbName, method)
    return returnStr
def _processFailed(dirName, nzbName):

    """Process a download that did not complete correctly"""

    returnStr = u""

    try:
        processor = failedProcessor.FailedProcessor(dirName, nzbName)
        process_result = processor.process()
        process_fail_message = ""
    except exceptions.FailedProcessingFailed, e:
        process_result = False
        process_fail_message = ex(e)

    returnStr += processor.log


    if sickbeard.DELETE_FAILED and process_result:
        returnStr += logHelper(u"Deleting folder of failed download " + dirName, logger.DEBUG)
        try:
            shutil.rmtree(dirName)
        except (OSError, IOError), e:
            returnStr += logHelper(u"Warning: Unable to remove the failed folder " + dirName + ": " + ex(e), logger.WARNING)

    if process_result:
        returnStr += logHelper(u"Processing succeeded: (" + str(nzbName) + ", " + dirName + ")")
    else:
        returnStr += logHelper(u"Processing failed: (" + str(nzbName) + ", " + dirName + "): " + process_fail_message, logger.WARNING)
    return returnStr


def _processNormal(dirName, nzbName=None, method=None, recurse=False):
    """Process a download that completed without issue"""

    returnStr = u""

    fileList = ek.ek(os.listdir, dirName)

    # split the list into video files and folders
    folders = filter(lambda x: ek.ek(os.path.isdir, ek.ek(os.path.join, dirName, x)), fileList)
    videoFiles = sorted(filter(helpers.isMediaFile, fileList), key=lambda x: os.path.getsize(ek.ek(os.path.join, dirName, x)), reverse=True)
    remaining_video_files = list(videoFiles)

    num_videoFiles = len(videoFiles)
    if num_videoFiles == 0 and len(folders) == 1:
        parent_nzbName = nzbName
    else:
        parent_nzbName = None
    # recursively process all the folders
    for cur_folder in folders:
        returnStr += u"\n"
        cur_folder = ek.ek(os.path.join, dirName, cur_folder)
        if helpers.is_hidden_folder(cur_folder):
            returnStr += logHelper(u"Ignoring hidden folder: " + cur_folder, logger.DEBUG)
        else:
            returnStr += logHelper(u"Recursively processing a folder: " + cur_folder, logger.DEBUG)
            returnStr += _processNormal(cur_folder, nzbName=parent_nzbName, method, recurse=True)

    remainingFolders = filter(lambda x: ek.ek(os.path.isdir, ek.ek(os.path.join, dirName, x)), fileList)

	
    if num_videoFiles == 0:
        returnStr += logHelper(u"There are no videofiles in folder: " + dirName, logger.DEBUG)
        if method != 'Manual':
            if delete_folder(dirName, check_empty=True):
                returnStr += logHelper(u"Deleted empty folder: " + dirName, logger.DEBUG)
    # If nzbName is set and there's more than one videofile in the folder, files will be lost (overwritten).
    if num_videoFiles >= 2:
        nzbName = None

    # process any files in the dir
    for cur_video_file in videoFiles:

        cur_video_file_path = ek.ek(os.path.join, dirName, cur_video_file)

        if method == 'Automatic':
            cur_video_file_path_size = ek.ek(os.path.getsize, cur_video_file_path)
            myDB = db.DBConnection()
            search_sql = "SELECT tv_episodes.tvdbid, history.resource FROM tv_episodes INNER JOIN history ON history.showid=tv_episodes.showid"
            search_sql += " WHERE history.season=tv_episodes.season and history.episode=tv_episodes.episode"
            search_sql += " and tv_episodes.status IN (" + ",".join([str(x) for x in common.Quality.DOWNLOADED]) + ")"
            search_sql += " and history.resource LIKE ? and tv_episodes.file_size = ?"
            sql_results = myDB.select(search_sql, [cur_video_file_path, cur_video_file_path_size])
            if len(sql_results):
                returnStr += logHelper(u"Ignoring file: " + cur_video_file_path + " looks like it's been processed already", logger.DEBUG)
                continue
        try:
            returnStr += u"\n"
            processor = postProcessor.PostProcessor(cur_video_file_path, nzb_name=nzbName, pp_options=pp_options)
            process_result = processor.process()
            process_fail_message = ""
        except exceptions.PostProcessingFailed, e:
            process_result = False
            process_fail_message = ex(e)

        except Exception, e:
            process_result = False
            process_fail_message = "Post Processor returned unhandled exception: " + ex(e)
        returnStr += processor.log 

        # as long as the postprocessing was successful delete the old folder unless the config wants us not to
        if process_result:

            remaining_video_files.remove(cur_video_file)

            if not sickbeard.KEEP_PROCESSED_DIR and len(remaining_video_files) == 0 and len(remainingFolders) == 0:
                if delete_folder(dirName, check_empty=False):
                    returnStr += logHelper(u"Deleted folder: " + dirName, logger.DEBUG)

            returnStr += logHelper(u"Processing succeeded for "+cur_video_file_path)

        else:
            returnStr += logHelper(u"Processing failed for " + cur_video_file_path + ": " + process_fail_message, logger.WARNING)
    return returnStr

