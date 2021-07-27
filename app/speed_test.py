import datetime
import statistics

from furl import furl

from api import ACMI_API_ENDPOINT, XOSAPI


class SpeedTest(XOSAPI):
    """
    An API speed test that calculates the average response time.
    """
    def __init__(self):
        super().__init__()
        self.uri = ACMI_API_ENDPOINT

    def start(self, resource='works'):
        """
        Get each page of index json files and return the average response time.
        """
        average_times = []
        total_requests = 0
        start = datetime.datetime.now()
        total_requests += 1
        works_json = self.get(resource).json()
        end = datetime.datetime.now()
        average_times.append((end - start).total_seconds())
        self.next_page = works_json.get('next')
        while self.next_page:
            params = furl(self.next_page).args
            start = datetime.datetime.now()
            total_requests += 1
            works_json = self.get(resource, params).json()
            end = datetime.datetime.now()
            average_times.append((end - start).total_seconds())
            self.next_page = works_json.get('next')
        average_request_time = round(statistics.mean(average_times) * 1000)
        print(
            f'Speed test finished.\nAverage time: {average_request_time} milliseconds\n'
            f'Requests: {len(average_times)}/{total_requests}'
        )
        return average_request_time


if __name__ == '__main__':
    print('======================')
    speed_test = SpeedTest()
    print(f'Starting speed test against: {speed_test.uri}')
    speed_test.start()
    print('======================')
