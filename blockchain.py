import hashlib
import json
from argparse import ArgumentParser
from time import time
from urllib.parse import urlparse
from uuid import uuid4

import requests
from flask import Flask, jsonify, request


class BlockChain(object):
    def __init__(self):
        # 储存区块链
        self.chain = []
        # 储存交易
        self.current_transactions = []
        # 储存节点
        self.nodes = set()

        # Create the genesis Block
        self.new_block(previous_hash=1, proof=100)

    def new_block(self, proof, previous_hash=None):
        """
        Create a new Block and adds it to the chain
        :param proof: <int> The proof given by the Proof of Work algorithm
        :param previous_hash: (Optional) <str> Hash of previous Block
        :return: <dict> New Block
        """
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }

        # Reset the current list of transactions
        self.current_transactions = []
        self.chain.append(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        # Adds a new transaction to the list of transactions
        """
        生成新交易信息，信息将加入到下一个待挖的区块中
        :param sender: <str> Address of the Sender
        :param recipient: <str> Address of the recipient
        :param amount: <int> Amount
        :return: <int> The index of the Block that will hold this transaction
        """
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })

        return self.last_block['index'] + 1

    @staticmethod
    def hash(block):
        # Hashes a Block
        """
        生成块的 SHA-256 hash值
        :param block: <dict> hash值
        :return: <str>
        """
        # We must make sure that the Dictionary is Ordered, or we will have inconsistent hashes
        # encode to bytes
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        # Returns the last Block in the chain
        return self.chain[-1]

    def proof_of_work(self, last_proof):
        """
        简单的工作量证明：
        - 查找一个p’使得hash(pp')以4个0开头
        - p是上一个块的证明， p'是当前的证明
        :param last_proof: <int>
        :return: <int>
        """
        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1
        return proof

    def register_node(self, address):
        """
        Add a new code to the list of nodes
        :param address: <str> Address of node. Eg. 'https://localhost:5001'
        :return: None
        """

        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def valid_chain(self, chain):
        """
        Determine if a given blockchain is valid
        :param chain: <list> A blockchain
        :return: <bool> True if valid, False if not
        """
        last_block = chain[0]
        current_index = 1
        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print('\n-----\n')
            # Check that the hash of the block is correct
            if block['previous_hash'] != self.hash(last_block):
                return False
            last_block = block
            current_index += 1
        return True

    def resolve_conflicts(self):
        """
        共识算法解决冲突
        使用网络中最长的链
        :return: <bool> True 如果链被取代，否则返回False
        """
        neighbors = self.nodes
        new_chain = None

        # We are only looking for chains longer than ours
        max_length = len(self.chain)

        # Grab and verify the chains from all the nodes in our network
        for node in neighbors:
            response = requests.get(f'http://{node}/chain')
            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # Check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # Replace our chain if we discovered a new, valiid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True
        return False

    @staticmethod
    def valid_proof(last_proof, proof):
        """
        验证证明：是否hash(last_proof, proof)以4个0开头
        :param last_proof: <int> Previous Proof
        :param proof: <int> Current Proof
        :return: <bool> True if correct, False if not
        """
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == '0000'

# Instantiate our Node
app = Flask(__name__)

# Generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-', '')

# Instantiate the BlockChain
block_chain = BlockChain()

@app.route('/mine', methods=['GET'])
def mine():
    # We run the proof of work algorithm to ge the next proof...
    last_block = block_chain.last_block
    last_proof = last_block['proof']
    proof = block_chain.proof_of_work(last_proof)

    # 给工作证明的节点提供奖励
    # 发送者为“0”表明是新挖出币
    block_chain.new_transaction(sender='0', recipient=node_identifier, amount=1,)

    # Forge the new Block by adding it to the chain
    block = block_chain.new_block(proof)

    response = {
        'message': 'New Block Forged',
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }

    return jsonify(response), 200

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()

    # Check that the required fields are in the Post'ed data
    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return 'Missing values', 400

    # Create a new Transaction
    index = block_chain.new_transaction(values['sender'], values['recipient'], values['amount'])

    response = {'message': f'Transaction will be added to Block {index}'}
    return jsonify(response), 201

@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': block_chain.chain,
        'length': len(block_chain.chain),
    }
    return jsonify(response), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()

    nodes = values.get('nodes')
    if nodes is None:
        return "Error: please supply a valid list of nodes", 400

    for node in nodes:
        block_chain.nodes.add(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(block_chain.nodes),
    }

    return jsonify(response), 201

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = block_chain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': block_chain.chain,
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': block_chain.chain,
        }
    return jsonify(response), 200

if __name__ == '__main__':
    # app.run(host='0.0.0.0', port=5000)
    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
    parser.add_argument('-add', '--address', default='0.0.0.0', type=str, help='address to host on')
    args = parser.parse_args()
    port = args.port
    add = args.address
    app.run(host=add, port=port)
