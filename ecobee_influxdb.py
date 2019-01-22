#!/bin/python3.6

# *************************************
#
# script to pull data from the Ecobee API and write to influxDB
# useful for making visualizations with Grafana, etc
#
#
# for now, you need to go to https://www.ecobee.com/home/developer/api/examples/ex1.shtml
# and follow the instructions to generate an API key, authorize the app with a PIN, and finally
# get a "refresh code"  The refresh code needs to be written to file ~/.ecobee_refresh_token on the first line
#
# you also need to enter your API key in the variables below
#
# **************************************

from influxdb import InfluxDBClient
import datetime
import requests
import json
import pytz
import sys
from pathlib import Path
import logging
import logging.handlers

#setup logging
log_file_path = 'ecobee.log'
days_of_logs_to_keep = 7
# set to DEBUG, INFO, ERROR, etc
logging_level = 'DEBUG'
#ecobee API Key
APIKey = "YOUR_API_KEY"
#influxDB info
influxdb_server = '192.168.1.2'
influxdb_port = 8086
influxdb_database = 'ecobee'
#runtime report time since last report query
runtime_difference = 60

#setup logger
logger = logging.getLogger('ecobee')
logger.setLevel(getattr(logging, logging_level))
handler = logging.handlers.TimedRotatingFileHandler(log_file_path, when="d", interval=1,  backupCount=days_of_logs_to_keep)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def to_bool(value):
    valid = {'true': True, 't': True, '1': True,
             'false': False, 'f': False, '0': False,
             }

    if isinstance(value, bool):
        return value

    lower_value = value.lower()
    if lower_value in valid:
        return valid[lower_value]
    else:
        raise ValueError('invalid literal for boolean: "%s"' % value)


def api_request(url, method, header=''):
    try:
        if method == 'post':
            #post to url
            return requests.post(url).json()
        if method == 'get':
            #get method
            return requests.get(url, headers=headers).json()
    except:
        logger.critical("error connecting to " + url)
        sys.exit()


#access token needs to be refreshed at least every hour
# get refresh code from file
token_file = str(Path.home()) + '/.ecobee_refresh_token'
with open(token_file) as f:
    refreshToken = f.readline().replace("\n","")

token_url = "https://api.ecobee.com/token?grant_type=refresh_token&code=" + refreshToken + "&client_id=" + APIKey
r = api_request(token_url, 'post')

access_token = r['access_token']
new_refresh_token = r['refresh_token']

with open(token_file, 'w') as f:
    f.write(new_refresh_token)

logger.debug("old refresh token = " + refreshToken)
logger.debug("access token = " + access_token)
logger.debug("new refresh token = " + new_refresh_token)


def logPoint(sensorName=None, thermostatName=None, sensorValue=None, sensorType=None):
    return {
        "measurement": sensorType,
        "tags": {
            "thermostat_name": thermostatName,
            "sensor": sensorName
        },
        "fields": {
            "value": sensorValue
        }
    }

client = InfluxDBClient(host=influxdb_server,
                        port=influxdb_port,
                        database=influxdb_database,
                        verify_ssl=False)


points = []

payload = {
    "selection": {
        "selectionType": "registered",
        "selectionMatch": "",
        "includeRuntime": True,
        "includeEquipmentStatus": True,
        "includeWeather": True,
        "includeSensors": True,
        "includeExtendedRuntime": True,
        "includeDevice": True,
        "includeEvents": True,
        "includeProgram": True
    }
}

payload = json.dumps(payload)

url = 'https://api.ecobee.com/1/thermostat?format=json&body=' + payload
headers = {'content-type': 'text/json', 'Authorization': 'Bearer ' + access_token}
response = api_request(url, 'get', headers)

point_count = 0

for thermostat in response['thermostatList']:
    thermostatName = thermostat['name']
    sensors = thermostat['remoteSensors']
    current_weather = thermostat['weather']['forecasts'][0]
    current_program = thermostat['program']['currentClimateRef']
    if len(thermostat['events']) > 0:
        current_program = thermostat['events'][0]['name']

    for sensor in sensors:
        for capability in sensor['capability']:
            if capability['type'] == 'occupancy':
                value = bool(to_bool(capability['value']))
                points.append(logPoint(sensorName=sensor['name'], thermostatName=str(thermostatName), sensorValue=bool(value), sensorType="occupancy"))
            if capability['type'] == 'temperature':
                if str.isdigit(capability['value']) > 0:
                    temp = int(capability['value']) / 10
                else:
                    temp = 0
                points.append(logPoint(sensorName=sensor['name'], thermostatName=str(thermostatName), sensorValue=float(temp), sensorType="temp"))
            if capability['type'] == 'humidity':
                points.append(logPoint(sensorName=sensor['name'], thermostatName=str(thermostatName), sensorValue=float(capability['value']), sensorType="humidity"))



    runtime = thermostat['runtime']
    temp = int(runtime['actualTemperature']) / 10
    heatTemp = int(runtime['desiredHeat']) / 10
    coolTemp = int(runtime['desiredCool']) / 10
    outside_temp = current_weather['temperature'] / 10
    outside_wind = current_weather['windSpeed']
    outside_humidity = current_weather['relativeHumidity']
    points.append(logPoint(sensorName=thermostatName, thermostatName=str(thermostatName), sensorValue=float(temp), sensorType="actualTemperature"))
    points.append(logPoint(sensorName=thermostatName, thermostatName=str(thermostatName), sensorValue=float(runtime['actualHumidity']), sensorType="actualHumidity"))
    points.append(logPoint(sensorName=thermostatName, thermostatName=str(thermostatName), sensorValue=float(heatTemp), sensorType="desiredHeat"))
    points.append(logPoint(sensorName=thermostatName, thermostatName=str(thermostatName), sensorValue=float(coolTemp), sensorType="desiredCool"))
    points.append(logPoint(sensorName=thermostatName, thermostatName=str(thermostatName), sensorValue=float(outside_temp), sensorType="outsideTemp"))
    points.append(logPoint(sensorName=thermostatName, thermostatName=str(thermostatName), sensorValue=float(outside_wind), sensorType="outsideWind"))
    points.append(logPoint(sensorName=thermostatName, thermostatName=str(thermostatName), sensorValue=float(outside_humidity), sensorType="outsideHumidity"))
    points.append(logPoint(sensorName=thermostatName, thermostatName=str(thermostatName), sensorValue=str(current_program), sensorType="currentProgram"))

    point_count += 1

client.write_points(points)

logger.info("sensor readings written: " + str(point_count))

#get historical runtime data

#clear points
points = []

#redefine logPoint
def logPoint(sensorName=None, sensorValue=None, sensorType=None,recordedTime=None):
    return {
        "measurement": sensorType,
        "time": recordedTime,
        "tags": {
            "sensor": sensorName
        },
        "fields": {
            "value": sensorValue
        }
    }

#set start date for runtime report to yesterday to cover querying right after midnight
#set end date to today to get most recent data
end_date = datetime.date.today()
start_date = end_date - datetime.timedelta(days=1)

for thermostat in response['thermostatList']:
    thermostatName = thermostat['name']
    #we only want to get runtime report every so often as it only updates about every 15-30 minutes
    #set variable "runtime_difference", recommend no quicker than 45 minute
    #  ex. if last data recorded is from 10:05, and data isn't updated until 10:35, then needs to be processed on
    #  the server it doesn't help to query the data again until ~10:45
    query = client.query("SELECT * FROM fantime WHERE sensor='" + thermostatName + "' ORDER BY DESC LIMIT 1")
    query_response = list(query.get_points())
    response_time_stamp = datetime.datetime.strptime(query_response[0]['time'], '%Y-%m-%dT%H:%M:%SZ')
    difference_minutes = (datetime.datetime.now() - response_time_stamp).seconds / 60

    logger.info("last runtime report timestamp from query for " + thermostatName + ": " + response_time_stamp.strftime("%Y-%m-%d %H:%M:%S"))
    logger.debug("difference in minutes: " + str(difference_minutes))

    if runtime_difference < difference_minutes:

        point_count = 0

        payload = {
            "startDate": start_date.strftime('%Y-%m-%d'),
            "endDate": end_date.strftime('%Y-%m-%d'),
            "columns": "auxHeat1,compCool1,fan,outdoorTemp,zoneAveTemp",
            "selection": {
               "selectionType": "thermostats",
               "selectionMatch": thermostat['identifier']
            }
        }

        payload = json.dumps(payload)

        url = 'https://api.ecobee.com/1/runtimeReport?format=json&body=' + payload
        headers = {'content-type': 'text/json', 'Authorization': 'Bearer ' + access_token}
        data = api_request(url, 'get', headers)

        for row in data['reportList'][0]['rowList']:
            myday,mytime,auxHeat1,compCool1,fan,outdoorTemp,zoneAveTemp,eol = row.split(",")
            date_str = str(myday) + " " + str(mytime)
            datetime_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            builttime = datetime_obj.strftime ("%Y-%m-%d %H:%M:%S")

            if datetime_obj > response_time_stamp:
                #we hit a row in the response that is newer than that last one recorded in influx

                #rows are returned up until the current time, but have empty strings in the columns if there is no data
                #rows with data, but with zero runtime have a 0
                if auxHeat1 is not '':
                        points.append(logPoint(sensorName=thermostatName, sensorValue=float(auxHeat1), sensorType="heattime", recordedTime=builttime))
                        point_count += 1
                        last_recorded_time = datetime_obj
                        logger.debug(thermostatName + " heat ran for " + auxHeat1 + " - " + builttime)
                if compCool1 is not '':
                        points.append(logPoint(sensorName=thermostatName, sensorValue=float(compCool1), sensorType="cooltime", recordedTime=builttime))
                        point_count += 1
                        last_recorded_time = datetime_obj
                        logger.debug(thermostatName + " cool ran for " + auxHeat1 + " - " + builttime)
                if fan is not '':
                        points.append(logPoint(sensorName=thermostatName, sensorValue=float(fan), sensorType="fantime", recordedTime=builttime))
                        point_count += 1
                        last_recorded_time = datetime_obj
                        logger.debug(thermostatName + " fan ran for " + auxHeat1 + " - " + builttime)

        logger.info(str(point_count) + " points written for runtime data from " + thermostatName)
    else:
        logger.info(thermostatName + " not queried as last query was less than " + str(runtime_difference) + " minutes ago")

logger.info("-----------------------------------")
client.write_points(points)

