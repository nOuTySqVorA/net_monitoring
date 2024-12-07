import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import plotly.graph_objs as go
from multiprocessing import Manager
import time
from ping3 import ping
import threading  # Use threading for background updates
import requests

# Monitored hosts configuration
monitored_hosts_ip = [] #list of IP addresses to be monitored: '192.168.0.1'
monitored_hosts_fqdn = [] #list of FQDNs to be displayed in description section of a table: Mikrotik(Cloud) and so on
monitored_hosts_abbrev = [] #list of abbreviations to be displayed by chart bars: M(C), which means Mikrotik(Cloud)
last_notification_time = 0
#####################################SECTION TO PUSH NOTIFICATIONS TO TELEGRAM CHAT#####################################
# Your bot's API token
bot_token = 'YOUR_BOT_TOKEN'
# The chat ID of the recipient
chat_id = 'YOUR_CHAT_ID'  # Use the actual chat ID or group ID

def send_message(chat_id, btoken, alert_notification):

    url = f'https://api.telegram.org/bot{btoken}/sendMessage'

    payload = {
    'chat_id': chat_id,
    'text': alert_notification
    }
    
    response = requests.post(url, json=payload)
    
    #verify, if request is successed
    """
    if response.status_code == 200:
        print("Message sent successfully!")
    else:
        print(f"Failed to send message: {response.status_code}, {response.text}")
    """
#############################################################################################################################

# hysteresis(our main metric using which the main monitoring statistic are displayed: which host is unreachable, which is reachable and has average ping latency)
UNAVAILABILITY_THRESHOLDS = 3

# notification interval
NOTIFICATION_INTERVAL = 120

############################################################################################################################

# this function determines all None variables in array. If all elements are None, function returns True
def host_unavailability(arr):
    return all(avg_ping is None for avg_ping in arr)

# this function calculate average ping by using passed array
def average_ping_latency(arr):
    valid_pings = [val for val in arr if val is not None]
    return round(sum(valid_pings) / len(valid_pings), 2) if valid_pings else None

# the main ping logic
def ping_host(hosts_ping_checking, host):

    unavailability_count = 0
    temp_arr = []
    # this function accomplishes 3 cycle of ping, each of them do 4 attemp to get icmp reply from pinged host
    ping_host_attempts = 4
    attempts_to_ping = 3

    for attempt in range(attempts_to_ping):
        for _ in range(ping_host_attempts):
            try:
                res = ping(host, timeout=1)
                temp_arr.append(round(res * 1000, 2) if res is not None else None)
            except Exception as e:
                temp_arr.append(None)
                # after each ping attempt(each of 4), function gets unavailability_count variable. If this unavailability_count = UNAVAILABILITY_THRESHOLDS - host is marked as unreachable
        if host_unavailability(temp_arr) == True:
                  unavailability_count +=1
        time.sleep(5)
    avg_ping = average_ping_latency(temp_arr)
    if unavailability_count >= UNAVAILABILITY_THRESHOLDS:
        hosts_ping_checking[host] = {'color': 'red', 'avg_ping': 'Unreachable'}
    else:
        hosts_ping_checking[host] = {'color': 'green', 'avg_ping': avg_ping}

# Background function to ping each host independently and keep updating
def background_ping_update(hosts_ping_checking):
    while True:  # Continuously ping the hosts
        processes = []
        for host in monitored_hosts_ip:
            pr_ping = threading.Thread(target=ping_host, args=(hosts_ping_checking, host))
            processes.append(pr_ping)

        # Start all threads
        for process in processes:
            process.start()

        # Wait for all threads to finish
        for process in processes:
            process.join()

        time.sleep(10)  # Wait 10 seconds before the next ping round

# Dash App Setup
app = dash.Dash(__name__)
app.title = "Network Monitoring"

# Layout
app.layout = html.Div([
    html.H1("Yavir Network Monitoring"),
    dcc.Graph(id='latency-chart'),
    dash_table.DataTable(
        id='monitoring-table',
        columns=[
            {'name': 'Abbreviations', 'id': 'abbrev'},
            {'name': 'Description', 'id': 'fqdn'},
            {'name': 'IP address', 'id': 'ip'},
            {'name': 'Average Ping Latency', 'id': 'avg_ping'},
        ],
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left'},
        style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'}
    ),
    dcc.Interval(id='interval-refresh', interval=30000, n_intervals=0)  # Refresh every 30 seconds
    """
    interval=30000: This specifies the interval in milliseconds between each "tick" or trigger of the Interval. 
    The value 30000 means that the interval will occur every 30,000 milliseconds, or 30 seconds.

    n_intervals=0: This is the initial number of intervals that have occurred. In this case, it starts at 0, meaning no interval has passed when the app first loads. 
    This value increments each time the interval is triggered.
    """

])

# Callback to Update Chart
@app.callback(
    [Output('latency-chart', 'figure'),
    Output('monitoring-table', 'data')],
    [Input('interval-refresh', 'n_intervals')] # when the interval counting expires, in this case is Input, our Outputs are updated. In this case, these are app's elements with id latency-chart and monitoring-table
)
def update_chart(n_intervals):

    global last_notification_time

    unavailable_hosts = []
    data = []
    avg_pings = []

    for i, host in enumerate(monitored_hosts_ip):
        unreachable_char_size = 100 # default char size, when host is unreachable
        status = hosts_net_availability.get(host, {'avg_ping': None, 'color': 'gray'})
        color = status['color']
        avg_ping = status['avg_ping'] if status['avg_ping'] != 'Unreachable' else unavailable_hosts.append(host) # if hosts_net_availability dictionary has avg_ping with properly average ping latency, this avg is appended to avg_pings array. If not, is appended to unavailable_hosts.append 
        avg_pings.append(avg_ping)
        data.append(go.Bar(
            x=[monitored_hosts_abbrev[i]],
            y=[avg_ping if avg_ping else unreachable_char_size],
            name=monitored_hosts_abbrev[i],
            marker_color=color,
            hoverinfo='text',
            hovertext=f"Avg Ping: {avg_ping}" if avg_ping else "Unreachable"
        ))

    # chech if notification need to be sent
    current_time = time.time()
    if len(unavailable_hosts) > 0:
        if current_time - last_notification_time > NOTIFICATION_INTERVAL:
            notification = f"Unreachable host(s): {','.join(unavailable_hosts)}"
            print(notification)
            last_notification_time = current_time


    # Prepare data for the table
    table_data = [{'abbrev': abbrev, 'fqdn': fqdn, 'ip': ip, 'avg_ping': avg_ping} 
                  for abbrev, fqdn, ip, avg_ping in zip(monitored_hosts_abbrev, 
                                                           monitored_hosts_fqdn, 
                                                           monitored_hosts_ip, avg_pings)]

    return {
        'data': data,
        'layout': go.Layout(
            title="Network(Ping) Availability",
            xaxis={'title': 'Hosts'},
            yaxis={'title': 'Latency (ms)'},
            barmode='group'
        )
    }, table_data

# Main Entry Point
if __name__ == '__main__':

    with Manager() as manager:
        hosts_net_availability = manager.dict()  # Shared dictionary for ping results

        # Start the background ping update in a separate thread
        ping_thread = threading.Thread(target=background_ping_update, args=(hosts_net_availability,))
        ping_thread.daemon = True  # Make it a daemon thread so it exits with the main program
        ping_thread.start()

        # Run Dash App
        app.run_server(debug=True)
