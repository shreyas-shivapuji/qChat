import asyncio
import websockets
import json
from random import getrandbits
from qiskit import QuantumCircuit, transpile
from qiskit_aer import Aer
from cryptography.fernet import Fernet
import hashlib
import base64

# Function for Bob to measure qubits with random bases
def measure_qubits(qubit_data):
    results = []
    bob_bases = [str(getrandbits(1)) for _ in range(len(qubit_data))]
    backend = Aer.get_backend('qasm_simulator')

    for i, qubit in enumerate(qubit_data):
        qc = QuantumCircuit(1, 1)
        if qubit["bit"] == "1":
            qc.x(0)  # Prepare |1>
        if qubit["basis"] == "1":
            qc.h(0)  # Alice's X basis
        if bob_bases[i] == "1":
            qc.h(0)  # Bob's X basis
        qc.measure(0, 0)
        tqc = transpile(qc, backend)
        job = backend.run(tqc, shots=1)
        result = job.result()
        measurement = int(result.get_counts().most_frequent())
        results.append({"measurement": measurement, "bob_basis": bob_bases[i]})

    return results, bob_bases

# Reconcile shared key by comparing bases with Alice
def reconcile_key(bob_bases, alice_bases, bob_results):
    shared_key = []
    for i in range(len(bob_bases)):
        if bob_bases[i] == alice_bases[i]:  # Use only matching bases
            shared_key.append(str(bob_results[i]["measurement"]))
    return "".join(shared_key)

# Generate a Fernet-compatible key from the shared key
def generate_fernet_key(shared_key):
    key_hash = hashlib.sha256(shared_key.encode()).digest()  # Get 32 bytes
    fernet_key = base64.urlsafe_b64encode(key_hash)  # Convert to base64
    return fernet_key

# Decrypt a message using the Fernet key
def decrypt_message(fernet_key, encrypted_message):
    cipher_suite = Fernet(fernet_key)
    decrypted_message = cipher_suite.decrypt(encrypted_message).decode()
    return decrypted_message

# WebSocket server function to handle Alice's connection and establish shared key
async def qubit_receiver(websocket, path):
    # Receive qubits data from Alice
    data = await websocket.recv()
    qubit_data = json.loads(data).get("qubit_data")
    
    # Measure received qubits
    bob_results, bob_bases = measure_qubits(qubit_data)
    
    # Send measurement results and bases back to Alice
    await websocket.send(json.dumps({"results": bob_results, "bob_bases": bob_bases}))

    # Receive encrypted message from Alice
    response = await websocket.recv()
    encrypted_message_base64 = json.loads(response).get("encrypted_message")
    
    # Decode the base64 encrypted message back to bytes
    encrypted_message = base64.b64decode(encrypted_message_base64)
    
    # Generate the shared key
    shared_key = reconcile_key(bob_bases, [q["basis"] for q in qubit_data], bob_results)
    print("Shared Key:", shared_key)

    # Generate a Fernet-compatible key
    fernet_key = generate_fernet_key(shared_key)

    # Decrypt the message from Alice
    decrypted_message = decrypt_message(fernet_key, encrypted_message)
    print("Decrypted message from Alice:", decrypted_message)

    # Send acknowledgment to Alice
    await websocket.send("Message received and decrypted successfully!")

# Start WebSocket server to listen to Alice
start_server = websockets.serve(qubit_receiver, "localhost", 8081)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
