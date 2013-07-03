# Author: Tyler Fenby <tylerfenby@gmail.com>
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

import re
import urllib
import datetime

from sickbeard import db
from sickbeard import logger
from sickbeard.history import dateFormat


def _log_helper(message, level=logger.MESSAGE):
    logger.log(message, level)
    return message + u"\n"


def prepareFailedName(release):
    """Standardizes release name for failed DB"""

    fixed = urllib.unquote(release)
    if(fixed.endswith(".nzb")):
        fixed = fixed.rpartition(".")[0]

    fixed = re.sub("[\.\-\+\ ]", "_", fixed)
    return fixed


def logFailed(release):
    log_str = u""
    size = -1
    provider = ""

    release = prepareFailedName(release)

    myDB = db.DBConnection("failed.db")
    sql_results = myDB.select("SELECT * FROM history WHERE release=?", [release])

    if len(sql_results) == 0:
        log_str += _log_helper(u"Release not found in snatch history. Recording it as bad with no size and no proivder.", logger.WARNING)
        log_str += _log_helper(u"Future releases of the same name from providers that don't return size will be skipped.", logger.WARNING)
    elif len(sql_results) > 1:
        log_str += _log_helper(u"Multiple logged snatches found for release", logger.WARNING)
        sizes = len(set(x["size"] for x in sql_results))
        providers = len(set(x["provider"] for x in sql_results))
        if sizes == 1:
            log_str += _log_helper(u"However, they're all the same size. Continuing with found size.", logger.WARNING)
            size = sql_results[0]["size"]
        else:
            log_str += _log_helper(u"They also vary in size. Deleting the logged snatches and recording this release with no size/provider", logger.WARNING)
            for result in sql_results:
                deleteLoggedSnatch(result["release"], result["size"], result["provider"])

        if providers == 1:
            log_str += _log_helper(u"They're also from the same provider. Using it as well.")
            provider = sql_results[0]["provider"]
    else:
        size = sql_results[0]["size"]
        provider = sql_results[0]["provider"]

    if not hasFailed(release, size, provider):
        myDB.action("INSERT INTO failed (release, size, provider) VALUES (?, ?, ?)", [release, size, provider])

    deleteLoggedSnatch(release, size, provider)

    return log_str


def hasFailed(release, size, provider="%"):
    """
    Returns True if a release has previously failed.

    If provider is given, return True only if the release is found
    with that specific provider. Otherwise, return True if the release
    is found with any provider.
    """

    myDB = db.DBConnection("failed.db")
    sql_results = myDB.select(
        "SELECT * FROM failed WHERE release=? AND size=? AND provider LIKE ?",
        [prepareFailedName(release), size, provider])

    return (len(sql_results) > 0)


def logSnatch(searchResult):
    myDB = db.DBConnection("failed.db")

    logDate = datetime.datetime.today().strftime(dateFormat)
    release = prepareFailedName(searchResult.name)

    providerClass = searchResult.provider
    if providerClass is not None:
        provider = providerClass.name
    else:
        provider = "unknown"

    myDB.action("INSERT INTO history (date, size, release, provider) VALUES (?, ?, ?, ?)",
                [logDate, searchResult.size, release, provider])


def deleteLoggedSnatch(release, size, provider):
    myDB = db.DBConnection("failed.db")

    release = prepareFailedName(release)

    myDB.action("DELETE FROM history WHERE release=? AND size=? AND provider=?",
                [release, size, provider])
