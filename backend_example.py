import json
import requests

# Define the backend URL
url = 'https://mindsearch-production.up.railway.app/solve'
headers = {'Content-Type': 'application/json'}

# Function to send a query to the backend and get the response
def get_response(query):
    # Prepare the input data
    data = {'inputs': [{'role': 'user', 'content': query}]}
    
    files = [(
'files', open('/home/umang_gupta/mindsearch-pdf/MindSearch/20230417 MS Mar23 Load Factors Remain Strong Updating Model.pdf', 'rb')  # Replace with your file path
    )]
    
    response = requests.post(url,
                                     data=data,
                                     files=files,
                                     timeout=20,
                                     stream=True
                                    )
    
    # Send the request to the backend
    # response = requests.post(url, headers=headers, data=json.dumps(data), timeout=20, stream=True)
    
    # Process the streaming response
    for chunk in response.iter_lines(chunk_size=8192, decode_unicode=False, delimiter=b'\n'):
        if chunk:
            decoded = chunk.decode('utf-8')
            if decoded == '\r':
                continue
            if decoded[:6] == 'data: ':
                decoded = decoded[6:]
            elif decoded.startswith(': ping - '):
                continue
            response_data = json.loads(decoded)
            agent_return = response_data['response']
            node_name = response_data['current_node']
            print(f"Node: {node_name}, Response: {agent_return['response']}")

# Example usage
if __name__ == '__main__':
    # query = ""
    query = "What is the weather like today in New York?"
    get_response(query)