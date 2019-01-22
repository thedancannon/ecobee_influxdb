# ecobee_influxdb

 script to pull data from the Ecobee API and write to influxDB
 useful for making visualizations with Grafana, etc


 for now, you need to go to https://www.ecobee.com/home/developer/api/examples/ex1.shtml
 and follow the instructions to generate an API key, authorize the app with a PIN, and finally
 get a "refresh code"  The refresh code needs to be written to file ~/.ecobee_refresh_token on the first line

 you also need to enter your API key in the variables below

