import React from 'react';
import { Loader2, WifiOff } from 'lucide-react';

const QRCodeDisplay = ({ qrCode, status, errorMessage }) => {
  console.log('QRCodeDisplay: Rendering', { qrCode, status, errorMessage });

  if (status === 'close') {
    return (
      <div className="text-center py-5">
        <div
          className="rounded-circle d-flex align-items-center justify-content-center mx-auto mb-4 bg-light opacity-25"
          style={{ width: '4rem', height: '4rem' }}
        >
          <WifiOff style={{ width: '2rem', height: '2rem' }} />
        </div>
        <p className="text-danger">
          {errorMessage || 'La conexión a WhatsApp está cerrada. Intenta actualizar el estado.'}
        </p>
      </div>
    );
  }

  if ((status === 'connecting' || status === 'pending' || status === 'disconnected') && !qrCode) {
    return (
      <div className="text-center py-5">
        <div className="d-inline-flex align-items-center gap-3 text-white">
          <Loader2 className="me-2 animate-spin" style={{ width: '1.5rem', height: '1.5rem' }} />
          <span className="h5 fw-medium">Generando código QR...</span>
        </div>
        <p className="text-muted mt-2">Estableciendo conexión con WhatsApp</p>
      </div>
    );
  }

  if ((status === 'connecting' || status === 'pending' || status === 'disconnected') && qrCode) {
    return (
      <div className="text-center">
        <h3 className="h4 fw-bold text-white mb-4">
          {status === 'pending' ? 'Escanea este código para activar tu cuenta' : 'Escanea este código para activar tu asistente'}
        </h3>
        <div className="relative inline-block">
          <div className="p-6 bg-white rounded-2xl shadow-2xl">
            <div className="w-64 h-64 bg-gray-100 rounded-lg flex items-center justify-center relative overflow-hidden">
              <img src={qrCode} alt="QR Code" className="w-64 h-64 mx-auto" />
            </div>
          </div>
          <div className="absolute inset-0 bg-gradient-to-r from-purple-600/20 to-blue-600/20 rounded-2xl blur-xl -z-10 scale-110"></div>
        </div>
        <div className="mt-6 space-y-2">
          <p className="text-gray-300 text-lg">Abre WhatsApp → Dispositivos Vinculados → Vincular Dispositivo</p>
          <p className="text-sm text-gray-400">El código expira en 25 segundos</p>
        </div>
        <div className="mt-4">
          <div className="w-full bg-white/10 rounded-full h-1 overflow-hidden">
            <div className="h-full bg-gradient-to-r from-purple-600 to-blue-600 rounded-full animate-pulse"></div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="text-center py-5">
      <div
        className="rounded-circle d-flex align-items-center justify-content-center mx-auto mb-4 bg-light opacity-25"
        style={{ width: '4rem', height: '4rem' }}
      >
        <svg style={{ width: '2rem', height: '2rem' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
      </div>
      <p className="text-danger">{errorMessage || 'No se puede mostrar el código QR en este estado.'}</p>
    </div>
  );
};

export default QRCodeDisplay;