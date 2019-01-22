import os
import re
import sys
import json
import datetime
import logging
import subprocess


from flask import Flask
from flask_restful import Resource, Api

logger = logging.basicConfig(level=logging.DEBUG)

application = Flask(__name__)
api = Api(application)

GITHUB_URL = "git@github.com:eventifyio/eventify.git"

class CdApi(Resource):
    """
    Continuous deployment API
    """
    # Initialize last_run
    last_run = datetime.datetime.now()

    def check_last_run(self):
        """
        Checks if a run has happened in the last 10 minutes to prevent
        recursive deployments
        """
        ten_mins_ago = datetime.datetime.now() - datetime.timedelta(seconds=600)
        if self.last_run > ten_mins_ago:
            return True
        return False

    @staticmethod
    def increment_version(version):
        """
        Increment minor version
        :param version: Current version
        :return: New version
        """
        parts = version.split('.')
        parts[2] = str(int(parts[2]) + 1)
        return '.'.join(parts)

    def write_version(self):
        """
        write version change to setup.py
        """
        version_pattern = re.compile("^\s+version='(\S+)'")
        url_pattern = re.compile("^\s+download_url='\S+eventify-(\d.\d.\d).tar.gz'")
        filename = "eventify/setup.py"
        new_data = ''

        # read and transpose
        with open(filename, 'r') as fh:
            data = fh.readlines()
            new_version = ''
            for line in data:
                groups = version_pattern.match(line)
                if groups:
                    version = groups.group(1)
                    new_version = self.increment_version(version)
                    line = line.replace(version, new_version)

                groups2 = url_pattern.match(line)
                if groups2:
                    version = groups2.group(1)
                    line = line.replace(version, new_version)
            
                new_data += line

        # write
        with open(filename, 'w') as fh:
            fh.write(new_data)
            fh.close()

    def post(self):
        """
        Handle POST Request from Jenkins
        """
        if self.check_last_run():
            return {"error": "Ran recently"}

        # get creds
        creds = self.get_config()

        # clean up
        subprocess.call(["rm", "-fr", "/www/api.sfkva.com/eventify"])

        # pull repo
        subprocess.call(["git", "clone", GITHUB_URL])

        # update the version
        self.write_version()

        # cd into repo
        os.chdir("eventify")

        # build distribution
        subprocess.call(["python", "setup.py", "sdist", "bdist_wheel"])

        # commit the code
        subprocess.call(["git", "add", "setup.py"])
        subprocess.call(["git", "add", "dist/"])
        subprocess.call(["git", "commit", "-m", "increment version"])
        subprocess.call(["git", "push", "origin", "master"])

        # publish to pypi
        username = creds['username']
        password = creds['password']
        subprocess.call(["twine", "upload", "dist/*", "-u", username, "-p", password])

        # set cd back
        os.chdir("..")

        # set last run
        self.last_run = datetime.datetime.now()

        return {
            "success": "Running deployment job"
        }

    @staticmethod
    def get_config():
        """
        Load config for pypi
        """
        with open('pypi.json') as fh:
            creds = json.load(fh)
        return creds
         
# Add route
api.add_resource(CdApi, '/')

if __name__ == '__main__':
    application.run(host='0.0.0.0')
