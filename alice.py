import asyncio
import websockets
import json
from random import getrandbits
from qiskit import QuantumCircuit, transpile
from qiskit_aer import Aer
from cryptography.fernet import Fernet
import hashlib
import base64

# Function to select random bits and bases for Alice
def select_encoding(length):
    alice_bitstring = "".join([str(getrandbits(1)) for _ in range(length)])
    alice_bases = "".join([str(getrandbits(1)) for _ in range(length)])
    return alice_bitstring, alice_bases

# Function to encode bits into qubits based on chosen bases
def encode(alice_bitstring, alice_bases):
    encoded_qubits = []
    for i in range(len(alice_bitstring)):
        qc = QuantumCircuit(1, 1)
        if alice_bases[i] == "1":
            qc.h(0)  # X basis
        if alice_bitstring[i] == "1":
            qc.x(0)  # Set state to |1>
        encoded_qubits.append(qc)
    return encoded_qubits

# Function to reconcile the key by comparing bases
def reconcile_key(alice_bases, bob_bases, alice_bitstring, bob_results):
    shared_key = []
    for i in range(len(alice_bases)):
        if alice_bases[i] == bob_bases[i]:  # Only use matching bases
            shared_key.append(alice_bitstring[i])
    return "".join(shared_key)

# Generate a Fernet-compatible key from the shared key
def generate_fernet_key(shared_key):
    key_hash = hashlib.sha256(shared_key.encode()).digest()  # Get 32 bytes
    fernet_key = base64.urlsafe_b64encode(key_hash)  # Convert to base64
    return fernet_key

# Encrypt a message using the Fernet key
def encrypt_message(fernet_key, message):
    cipher_suite = Fernet(fernet_key)
    encrypted_message = cipher_suite.encrypt(message.encode())
    return encrypted_message

# Main function to send qubits and establish a shared key with Bob
async def send_qubits_and_reconcile(qubit_data, alice_bases, alice_bitstring, bob_address="ws://localhost:8081"):
    async with websockets.connect(bob_address) as websocket:
        # Send qubits data to Bob
        await websocket.send(json.dumps({"qubit_data": qubit_data}))

        # Receive Bob's measurement results and bases
        response = await websocket.recv()
        bob_response = json.loads(response)
        bob_results = bob_response.get("results")
        bob_bases = bob_response.get("bob_bases")

        # Reconcile the shared key
        shared_key = reconcile_key(alice_bases, bob_bases, alice_bitstring, bob_results)
        print("Shared Key:", shared_key)

        # Generate a Fernet-compatible key
        fernet_key = generate_fernet_key(shared_key)

        # Encrypt a message to send to Bob
        message = "Hello Bob, this is a secure message!"
        encrypted_message = encrypt_message(fernet_key, message)
        
        # Convert encrypted message to base64 string
        encrypted_message_base64 = base64.b64encode(encrypted_message).decode('utf-8')
        print("Encrypted message to Bob:", encrypted_message_base64)

        # Send the encrypted message to Bob
        await websocket.send(json.dumps({"encrypted_message": encrypted_message_base64}))
        ack = await websocket.recv()
        print("Received from Bob:", ack)

# Start the key exchange process with Bob
async def start_qkd_with_bob(num_bits=10):
    bitstring, bases = select_encoding(num_bits)
    qubit_data = [{"bit": bitstring[i], "basis": bases[i]} for i in range(num_bits)]
    await send_qubits_and_reconcile(qubit_data, bases, bitstring)

# Run the program
asyncio.run(start_qkd_with_bob())
