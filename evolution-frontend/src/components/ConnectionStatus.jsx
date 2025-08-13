import React from 'react';
import { Badge } from './ui/badge';

const ConnectionStatus = ({ status, connectedUser }) => {
  const isConnected = status === 'open';
  const isConnecting = status === 'connecting';
  const isPending = status === 'pending';
  const isDisconnected = !isConnected && !isConnecting && !isPending;

  return (
    <div className="p-3">
      <h3 className="h5 fw-bold text-white mb-3">Estado del Asistente</h3>
      <div className="d-flex align-items-center gap-3 mb-3">
        <div
          className={`rounded-circle d-flex align-items-center justify-content-center p-2 ${
            isConnected ? 'bg-success' : isConnecting ? 'bg-warning' : isPending ? 'bg-warning' : 'bg-danger'
          }`}
          style={{ width: '2.5rem', height: '2.5rem' }}
        >
          {isConnected ? (
            <svg className="text-white" style={{ width: '1.5rem', height: '1.5rem' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          ) : (
            <svg className="text-white" style={{ width: '1.5rem', height: '1.5rem' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          )}
        </div>
        <div>
          <p className="fw-medium mb-1 text-dark">Estado de WhatsApp</p>
          <p
            className={`mb-0 ${
              isConnected ? 'text-success' : isConnecting ? 'text-warning' : isPending ? 'text-warning' : 'text-danger'
            }`}
          >
            {isConnected
              ? `Conectado (${connectedUser?.phone || 'Número desconocido'})`
              : isConnecting
              ? 'Conectando...'
              : isPending
              ? 'Pendiente de activación (escanea el código QR)'
              : 'Desconectado'}
          </p>
        </div>
      </div>
      <div className="d-flex align-items-center gap-3">
        <div
          className={`rounded-circle d-flex align-items-center justify-content-center p-2 ${isConnected ? 'bg-success' : 'bg-danger'}`}
          style={{ width: '2.5rem', height: '2.5rem' }}
        >
          <svg className="text-white" style={{ width: '1.5rem', height: '1.5rem' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
            />
          </svg>
        </div>
        <div>
          <p className="fw-medium mb-1 text-dark">Asistente</p>
          <p className={`mb-0 ${isConnected ? 'text-success' : 'text-danger'}`}>
            {isConnected ? 'Activo' : isPending ? 'Pendiente' : 'Inactivo'}
          </p>
        </div>
      </div>
      {isPending && (
        <div className="mt-3">
          <Badge variant="warning">Esperando activación: Escanea el código QR para activar el asistente</Badge>
        </div>
      )}
    </div>
  );
};

export default ConnectionStatus;