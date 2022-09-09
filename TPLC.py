# 3PLC Tracking Addon
# Default Packages
import pathlib
import traceback
from datetime import datetime
from datetime import timedelta
import json
import requests
import math
import logging

class Loggable:
	logger = logging.getLogger()

# Start:
# ct = CharmedTracker().main()
class TPLCTrackingAddon(Loggable):
	def __init__(self):
		self.config = Storage(filepath="./resources/config.json")
		self.api = WMS_API(config=self.config)

	def main(self):
		response_1 = self.api.get_order("18484135")
		print(json.dumps(response_1.json(), indent=1))
		
		#if response_1.status_code == 200:
		#	response_2 = self.api.set_order_to_shipped("17021065", response_1.headers.get("etag"))
		#	print(json.dumps(response_2.json(), indent=1))

class Storage(Loggable):
	'''Allows access to data stored on disk'''
	def __init__(self, filepath: str, default_value=None):
		'''
		param filepath: path to .json file
		param default_value: default value for self.data
		'''
		if filepath[-5:] != ".json":
			raise AttributeError("Filepath must point to a valid .json file")
		self.filepath = filepath
		self.default_value = default_value
		self.data = self.load()

	def load(self) -> dict:
		try:
			with open(self.filepath, "r") as file:
				self.data = json.load(file)
		except FileNotFoundError:
			self.data = self.default_value
			with open(self.filepath, "x") as file:
				json.dump(self.data, file)
		return self.data

	def save(self):
		with open(self.filepath, "w") as file:
			json.dump(self.data, file, indent=4)

	def data(self) -> object:
		'''Returns the object stored by Storage'''
		return self.data

class StoredList(Storage, Loggable):
	'''Extends Storage to function as a list with item indexes (for sorting)'''
	#Note: generalize to remove dependency on Storage?
	def __init__(self, filepath, default_value=None, default_index_function=None):
		'''
		param filepath: see Storage
		param default_value: see Storage
		param default_index_function: called when trying to add() to StoredList without an index param. Defaults to next_index()
		'''
		if default_value == None:
			default_value = []
		if default_index_function == None:
			self.index_counter = -1
			self.index_function = self.next_index
		super().__init__(filepath, default_value)
	
	def add(self, value, index=None):
		'''
		param value: value to be added
		param index: index to be added to value. Defaults to self.index_function() if missing
		'''
		if index == None:
			index = self.index_function()
		value._index = index
		if value not in self.data:
			self.data.append(value)

	def remove(self, value):
		if value in self.data:
			del value

	def next_index(self) -> int:
		self.index_counter += 1
		return self.index_counter

def today():
	return datetime.strftime(datetime.now(), "%Y-%m-%d")

def now():
	return datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")

class WMS_API(Loggable):
	'''Gets orders data from 3PLC'''
	BYTES_USED = 0

	def __init__(self, config: Storage):
		'''
		params config: json file with config information
		'''
		self.config = config
		self.token = config.data["token"]
		token = self.get_token()
		if token:
			self.logger.info("3PLC access token refreshed")

	def get_token(self) -> dict:
		'''Returns a valid 3PLC access token, refreshing if needed'''
		creation_time = datetime.strptime(self.token.get("creation_time"), "%Y-%m-%d %H:%M:%S")
		token_duration = timedelta(seconds = self.token["contents"]["expires_in"])
		if datetime.now() > (creation_time + token_duration):
			token = self._refresh_token()
			if token:
				self.config.data["token"]["contents"] = token
				self.config.data["token"]["creation_time"] = datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")
				self.config.save()
				self.token = self.config.data["token"]
		return self.token
	
	def _refresh_token(self) -> dict:
		host_url = "https://secure-wms.com/AuthServer/api/Token"
		headers = {
			"Content-Type": "application/json; charset=utf-8",
			"Accept": "application/json",
			"Host": "secure-wms.com",
			"Accept-Language": "Content-Length",
			"Accept-Encoding": "gzip,deflate,sdch",
			"Authorization": "Basic " + self.config.data["auth_key"]
		}
		payload = json.dumps({
			"grant_type": "client_credentials",
			"tpl": self.config.data["tpl"],
			"user_login_id": self.config.data["user_login_id"]
		})

		response = requests.request("POST", host_url, data = payload, headers = headers, timeout = 3.0)
		self.log_data_usage(response) #TODO decorator
		if response.status_code == 200: #HTTP 200 == OK
			return response.json()
		else:
			self.logger.error("Unable to refresh token")
			self.logger.error(response.text)
		return None

	def log_data_usage(self, request):
		'''Cuz higher-ups see the API usage bill
		Current estimate is ~2kb for a request (w/only Contacts)
		'''
		method_len = len(request.request.method)
		url_len = len(request.request.url)
		headers_len = len('\r\n'.join('{}{}'.format(key, value) for key, value in request.request.headers.items()))
		body_len = len(request.request.body if request.request.body else [])
		text_len = len(request.text)
		approx_len = method_len + url_len + headers_len + body_len + text_len
		self.logger.info(f"Used approx. {str(approx_len)} bytes")
		return approx_len

	def get_order(self, order_id):
		url = f"https://secure-wms.com/orders/{order_id}?detail=all"
		headers = {
			"Content-Type": "application/json; charset=utf-8",
			"Accept": "application/json",
			"Host": "secure-wms.com",
			"Accept-Language": "Content-Length",
			"Accept-Encoding": "gzip,deflate,sdch",
			"Authorization": "Bearer " + self.config.data["token"]["contents"]["access_token"]
		}
		response = requests.request("GET", url, data = {}, headers = headers, timeout = 30.0)
		self.log_data_usage(response)
		return response

	def set_order_to_shipped(self, order_id, etag):
		url = f"https://secure-wms.com/orders/{order_id}/packages"
		payload = "{\"package\": [{\"packageId\": 2554,\"packageTypeId\": 2,\"length\": 8,\"width\": 7.5,\"height\": 3,\"weight\": 0.25,\"codAmount\": 0,\"insuredAmount\": 0,\"TrackingNumber\":\"124789\",\"createDate\": \"2019-04-30T21:40:45.69\",\"readOnly\": {\"oversize\": false,\"cod\": false,\"ucc128\": 1110},\"packagecontents\": [{\"packageContentId\": 2560,\"packageId\": 2554,\"orderItemId\": 294,\"receiveItemId\": 3,\"qty\": 1,\"lotNumber\": \"\",\"serialNumber\": \"\",\"createDate\": \"2019-04-30T21:40:45.69\",\"serialNumbers\": []}]},{\"packageId\": 2555,\"packageTypeId\": 2,\"length\": 8,\"width\": 7.5,\"height\": 3,\"weight\": 0.25,\"codAmount\": 0,\"insuredAmount\": 0,\"TrackingNumber\":\"124789\",\"createDate\": \"2019-04-30T21:40:45.69\",\"readOnly\": {\"oversize\": false,\"cod\": false,\"ucc128\": 1109},\"packagecontents\": [{\"packageContentId\": 2561,\"packageId\": 2555,\"orderItemId\": 294,\"receiveItemId\": 3,\"qty\": 1,\"lotNumber\": \"\",\"serialNumber\": \"\",\"createDate\": \"2019-04-30T21:40:45.69\",\"serialNumbers\": []}]},{\"packageId\": 2556,\"packageTypeId\": 2,\"length\": 8,\"width\": 7.5,\"height\": 3,\"weight\": 0.25,\"codAmount\": 0,\"insuredAmount\": 0,\"TrackingNumber\":\"124789\",\"createDate\": \"2019-04-30T21:40:45.69\",\"readOnly\": {\"oversize\": false,\"cod\": false,\"ucc128\": 1108},\"packagecontent\": [{\"packageContentId\": 2562,\"packageId\": 2556,\"orderItemId\": 294,\"receiveItemId\": 3,\"qty\": 1,\"lotNumber\": \"\",\"serialNumber\": \"\",\"createDate\": \"2019-04-30T21:40:45.69\",\"serialNumbers\": []}]}]}"
		#payload = "{\"Notes\":  \"Hello world\",\"ReferenceNum\": \"Test-0342\"}"
		headers = {
			"Content-Type": "application/json; charset=utf-8",
			"Accept": "application/json",
			"Host": "secure-wms.com",
			"Accept-Language": "Content-Length",
			"Accept-Encoding": "gzip,deflate,sdch",
			"Authorization": "Bearer " + self.config.data["token"]["contents"]["access_token"],
			"If-Match": etag
		}
		response = requests.request("PUT", url, data = payload, headers = headers, timeout = 30.0)
		return response

def init_logging():
	logger = logging.getLogger()
	logger.setLevel(logging.INFO)
	#
	file_handler = logging.FileHandler("./resources/log.txt")
	file_handler.setLevel(logging.ERROR)
	#
	console_handler = logging.StreamHandler()
	console_handler.setLevel(logging.DEBUG)
	#
	formatter = logging.Formatter(fmt="%(asctime)s %(levelname)s %(message)s", datefmt="%Y%m%d%H%M%S")
	file_handler.setFormatter(formatter)
	console_handler.setFormatter(formatter)
	#
	logger.addHandler(file_handler)
	logger.addHandler(console_handler)
	#
	logger.info("init CharmedTracker_V3")

if __name__ == "__main__":
	init_logging()
	TPLCTrackingAddon().main()
	
