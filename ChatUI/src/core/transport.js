// Simple AG2 Transport
import { processMessage, handleAction } from './agentManager';

class AG2Transport {
  constructor() {
    this.ws = null;
    this.handlers = new Map();
    this.connect();
  }

  connect() {
    const wsUrl = process.env.REACT_APP_WS_URL || 'ws://localhost:8000/ws';
    this.ws = new WebSocket(wsUrl);
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(data);
    };
    
    this.ws.onopen = () => console.log('Connected to AG2');
    this.ws.onerror = (e) => console.error('AG2 error:', e);
  }

  async handleMessage(message) {
    // Route to handlers or process with agents
    if (this.handlers.has(message.type)) {
      this.handlers.get(message.type)(message);
    } else {
      const response = await processMessage(message);
      if (response) {
        this.send({ type: 'response', data: response });
      }
    }
  }

  send(data) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  on(type, handler) {
    this.handlers.set(type, handler);
  }
}

const transport = new AG2Transport();

export const send = (data) => transport.send(data);
export const on = (type, handler) => transport.on(type, handler);
export default transport;
