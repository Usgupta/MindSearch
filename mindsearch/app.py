import asyncio
import json
import logging
from copy import deepcopy
from dataclasses import asdict
from typing import Dict, List, Union, Optional

import janus
from fastapi.middleware.cors import CORSMiddleware
from lagent.schema import AgentStatusCode
from sse_starlette.sse import EventSourceResponse

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from fastapi.encoders import jsonable_encoder

from mindsearch.agent import init_agent


from json import JSONDecodeError
import ast


def parse_arguments():
    import argparse
    parser = argparse.ArgumentParser(description='MindSearch API')
    parser.add_argument('--lang', default='cn', type=str, help='Language')
    parser.add_argument('--model_format',
                        default='internlm_server',
                        type=str,
                        help='Model format')
    parser.add_argument('--search_engine',
                       default='DuckDuckGoSearch',
                       type=str,
                       help='Search engine')
    return parser.parse_args()


args = parse_arguments()
app = FastAPI(docs_url='/')

app.add_middleware(CORSMiddleware,
                   allow_origins=['*'],
                   allow_credentials=True,
                   allow_methods=['*'],
                   allow_headers=['*'])


def checker(data: str = Form(...)):
    try:
       return json.loads(data)
    except JSONDecodeError:
        raise HTTPException(status_code=400, detail='Invalid JSON data')



class GenerationParams(BaseModel):
    inputs: Union[str, List[Dict]]
    agent_cfg: Dict = dict()
    

# def parse_json(data: str = Form(...)):
#     try:
#         return GenerationParams.model_validate_json(data)
#     except ValidationError as e:
#         raise HTTPException(
#             detail=jsonable_encoder(e.errors()),
#             status_code=422,
#         )

# @app.post("/submit1")
# def submit(
#     name: str = Form(...),
#     point: float = Form(...),
#     is_accepted: bool = Form(...),
#     inputs: List = Form(...),
#     files: List[UploadFile] = File(...),
# ):
#     return {
#         "JSON Payload": {"name": name, "point": point, "is_accepted": is_accepted,"inputs":inputs},
#         "Filenames": [file.filename for file in files],
#     }

@app.post('/solve')
async def run(
    inputs: List = Form(...),
    files: List[UploadFile] = File(...),):
    
    print({
        "JSON Payload": {"inputs":inputs},
        "Filenames": [file.filename for file in files],
    })
    
    print(type(inputs))
    
    print(inputs)
    
    inputs_json = ast.literal_eval(inputs[0])
    
    inputs[0] = inputs_json
    
    # print(inputs_json)
    
    # print({"inputs": params.inputs,
    #     "agent_cfg": params.agent_cfg,
    #     "filenames": [file.filename for file in files]})

    def convert_adjacency_to_tree(adjacency_input, root_name):

        def build_tree(node_name):
            node = {'name': node_name, 'children': []}
            if node_name in adjacency_input:
                for child in adjacency_input[node_name]:
                    child_node = build_tree(child['name'])
                    child_node['state'] = child['state']
                    child_node['id'] = child['id']
                    node['children'].append(child_node)
            return node

        return build_tree(root_name)

    async def generate():
        try:
            queue = janus.Queue()
            stop_event = asyncio.Event()

            # Wrapping a sync generator as an async generator using run_in_executor
            def sync_generator_wrapper():
                try:
                    for response in agent.stream_chat(inputs):
                        queue.sync_q.put(response)
                except Exception as e:
                    logging.exception(
                        f'Exception in sync_generator_wrapper: {e}')
                finally:
                    # Notify async_generator_wrapper that the data generation is complete.
                    queue.sync_q.put(None)

            async def async_generator_wrapper():
                loop = asyncio.get_event_loop()
                loop.run_in_executor(None, sync_generator_wrapper)
                while True:
                    response = await queue.async_q.get()
                    if response is None:  # Ensure that all elements are consumed
                        break
                    yield response
                    if not isinstance(
                            response,
                            tuple) and response.state == AgentStatusCode.END:
                        break
                stop_event.set()  # Inform sync_generator_wrapper to stop

            async for response in async_generator_wrapper():
                if isinstance(response, tuple):
                    agent_return, node_name = response
                else:
                    agent_return = response
                    node_name = None
                origin_adj = deepcopy(agent_return.adjacency_list)
                adjacency_list = convert_adjacency_to_tree(
                    agent_return.adjacency_list, 'root')
                assert adjacency_list[
                    'name'] == 'root' and 'children' in adjacency_list
                agent_return.adjacency_list = adjacency_list['children']
                agent_return = asdict(agent_return)
                agent_return['adj'] = origin_adj
                response_json = json.dumps(dict(response=agent_return,
                                                current_node=node_name),
                                           ensure_ascii=False)
                yield {'data': response_json}
                # yield f'data: {response_json}\n\n'
        except Exception as exc:
            msg = 'An error occurred while generating the response.'
            logging.exception(msg)
            response_json = json.dumps(
                dict(error=dict(msg=msg, details=str(exc))),
                ensure_ascii=False)
            yield {'data': response_json}
            # yield f'data: {response_json}\n\n'
        finally:
            await stop_event.wait(
            )  # Waiting for async_generator_wrapper to stop
            queue.close()
            await queue.wait_closed()

    inputs = inputs

    agent = init_agent(lang=args.lang, model_format=args.model_format,search_engine=args.search_engine,files=files)
    return EventSourceResponse(generate())


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8002, log_level='info')
