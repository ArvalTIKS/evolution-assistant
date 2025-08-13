import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { toast, ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import { Card } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Separator } from './ui/separator';
import ConnectionStatus from './ConnectionStatus';
import QRCodeDisplay from './QRCodeDisplay';
import AssistantInfo from './AssistantInfo';

// Robust backend URL detection
const getBackendUrl = () => {
  if (import.meta.env.VITE_BACKEND_URL) {
    console.log('Using VITE_BACKEND_URL:', import.meta.env.VITE_BACKEND_URL);
    return import.meta.env.VITE_BACKEND_URL;
  }
  const currentHost = window.location.hostname;
  const currentProtocol = window.location.protocol;
  if (
    currentHost.includes('.preview.emergentagent.com') ||
    currentHost.includes('.emergent.host') ||
    currentHost.includes('emergent')
  ) {
    const backendUrl = `${currentProtocol}//${currentHost.replace('frontend', 'backend')}`;
    console.log('Detected EMERGENT environment:', backendUrl);
    return backendUrl;
  }
  const devUrl = 'http://localhost:8000';
  console.log('Using DEVELOPMENT fallback:', devUrl);
  return devUrl;
};

const API_BASE = getBackendUrl();
const AUTH_TOKEN = import.meta.env.VITE_AUTH_TOKEN;

const QRAssistantPage = () => {
  const { unique_url } = useParams();
  const [clientData, setClientData] = useState(null);
  const [qrCode, setQrCode] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const qrTimerRef = useRef(null);
  const statusTimerRef = useRef(null);
  const retryCountRef = useRef(0);
  const maxRetries = 3;

  const fetchQRCode = useCallback(async (instance_id) => {
    if (clientData?.whatsapp?.connected) {
      setQrCode(null);
      return;
    }

    try {
      setRefreshing(true);
      const response = await axios.get(`${API_BASE}/client/${instance_id}/qr`, {
        headers: AUTH_TOKEN ? { Authorization: `Bearer ${AUTH_TOKEN}` } : {},
        timeout: 30000,
      });
      console.log('QR response:', response.data);

      if (response.data.qr) {
        setQrCode(response.data.qr);
        setErrorMessage(null);
        retryCountRef.current = 0;
      } else {
        setQrCode(null);
        setErrorMessage(response.data.error || 'No se pudo cargar el código QR.');
      }
    } catch (error) {
      console.error('Error fetching QR code:', error);
      setQrCode(null);
      const errorMsg =
        error.response?.data?.detail || 'Error al conectar con el servidor.';
      setErrorMessage(errorMsg);
      if (
        errorMsg.includes('Instance') &&
        errorMsg.includes('does not exist') &&
        retryCountRef.current < maxRetries
      ) {
        retryCountRef.current += 1;
        console.log(`Instance not found, retrying (${retryCountRef.current}/${maxRetries})...`);
        await new Promise((resolve) => setTimeout(resolve, 2000));
        await fetchQRCode(instance_id);
      } else {
        toast.error(errorMsg);
      }
    } finally {
      setRefreshing(false);
    }
  }, [clientData]);

  const fetchClientData = useCallback(async () => {
    try {
      setRefreshing(true);
      setLoading(true);
      const landingResponse = await axios.get(`${API_BASE}/client/${unique_url}/landing`, {
        headers: AUTH_TOKEN ? { Authorization: `Bearer ${AUTH_TOKEN}` } : {},
        timeout: 30000,
      });
      console.log('Landing response:', landingResponse.data);
      const client = landingResponse.data;

      const statusResponse = await axios.get(`${API_BASE}/client/${client.id}/status`, {
        headers: AUTH_TOKEN ? { Authorization: `Bearer ${AUTH_TOKEN}` } : {},
        timeout: 30000,
      });
      console.log('Status response:', statusResponse.data);

      setClientData({
        client: {
          id: client.id,
          name: client.name,
          email: client.email,
          status: client.status, // pending, active
          messageCount: 0, // Not provided by backend
          pausedCount: 0, // Not provided by backend
          globalPause: false, // Not provided by backend
        },
        whatsapp: {
          connected: client.connected,
          status: statusResponse.data.status, // open, connecting, close
          connected_phone: client.connected_phone || null,
        },
      });
      setErrorMessage(null);

      if (statusResponse.data.status !== 'open') {
        await fetchQRCode(client.id);
      } else {
        setQrCode(null);
      }
    } catch (error) {
      console.error('Error checking connection status:', error);
      setQrCode(null);
      setErrorMessage(
        error.response?.status === 404
          ? 'Cliente no encontrado. Verifica que el enlace sea correcto o contacta al administrador (contacto@tiks.cl).'
          : error.response?.status === 403
          ? 'Error de autenticación con el servidor de WhatsApp. Contacta al administrador.'
          : 'Error al verificar el estado.'
      );
      toast.error(errorMessage || 'Error desconocido al conectar con el servidor.');
    } finally {
      console.log('fetchClientData: Clearing loading state');
      setLoading(false);
      setRefreshing(false);
    }
  }, [unique_url, fetchQRCode, errorMessage]);

  const handleDisconnect = async () => {
    if (!clientData?.client?.id) {
      toast.error('No se encontró el ID del cliente. Intenta nuevamente.');
      return;
    }
    if (
      !window.confirm(
        '¿Estás seguro que quieres desvincular WhatsApp? Esto eliminará el dispositivo de tu lista de dispositivos vinculados.'
      )
    ) {
      return;
    }
    setRefreshing(true);
    try {
      // Use admin toggle endpoint (temporary, replace with client-specific endpoint)
      await axios.post(
        `${API_BASE}/admin/clients/${clientData.client.id}/toggle`,
        { action: 'disconnect' },
        {
          headers: AUTH_TOKEN ? { Authorization: `Bearer ${AUTH_TOKEN}` } : {},
          timeout: 30000,
        }
      );
      toast.success('✅ WhatsApp desvinculado exitosamente.');
      await fetchClientData();
    } catch (error) {
      console.error('Error disconnecting WhatsApp:', error);
      const errorMsg = error.response?.data?.detail || 'Error al desvincular WhatsApp.';
      toast.error(errorMsg);
    } finally {
      setRefreshing(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    retryCountRef.current = 0;
    await fetchClientData();
  };

  useEffect(() => {
    console.log('useEffect: Initial load');
    const loadData = async () => {
      try {
        setLoading(true);
        await fetchClientData();
      } catch (err) {
        console.error('useEffect: Error in initial load', err);
        setErrorMessage('Error al cargar los datos iniciales. Por favor intenta nuevamente.');
      } finally {
        console.log('useEffect: Clearing initial loading state');
        setLoading(false);
      }
    };
    loadData();

    statusTimerRef.current = setInterval(() => {
      console.log('useEffect: Status interval triggered');
      fetchClientData();
    }, 30000);

    qrTimerRef.current = setInterval(() => {
      if (clientData?.whatsapp?.connected) return;
      fetchQRCode(clientData?.client?.id);
    }, 25000);

    return () => {
      console.log('useEffect: Cleanup intervals');
      clearInterval(statusTimerRef.current);
      clearInterval(qrTimerRef.current);
    };
  }, [fetchClientData, fetchQRCode, clientData?.client?.id]);

  if (!unique_url) {
    console.error('Render: No unique_url provided');
    return (
      <div className="min-vh-100 bg-dark d-flex align-items-center justify-content-center">
        <div className="text-center text-white">
          <p>Error: Enlace inválido. Verifica la URL e intenta nuevamente.</p>
          <Button
            onClick={() => window.location.reload()}
            className="btn btn-outline-light mt-4"
          >
            Recargar Página
          </Button>
        </div>
      </div>
    );
  }

  if (loading) {
    console.log('Render: Loading state');
    return (
      <div className="min-vh-100 bg-dark d-flex align-items-center justify-content-center">
        <div className="text-center">
          <div className="spinner-border text-white mx-auto mb-4" role="status">
            <span className="visually-hidden">Cargando...</span>
          </div>
          <p className="text-white">Cargando plataforma...</p>
        </div>
      </div>
    );
  }

  if (errorMessage && !clientData) {
    console.log('Render: Error state', errorMessage);
    return (
      <div className="min-vh-100 bg-dark d-flex align-items-center justify-content-center">
        <div className="text-center text-white">
          <p>{errorMessage}</p>
          <Button
            onClick={handleRefresh}
            className="btn btn-outline-light mt-4"
            disabled={refreshing}
          >
            {refreshing ? 'Verificando...' : 'Intentar de nuevo'}
          </Button>
        </div>
      </div>
    );
  }

  console.log('Render: Main UI', { clientData, qrCode, errorMessage });

  return (
    <div className="min-vh-100 bg-dark">
      <div className="position-relative z-1 container py-5">
        <div className="text-center mb-5">
          <div className="d-inline-flex align-items-center gap-3 mb-3">
            <div
              className="rounded-3 d-flex align-items-center justify-content-center"
              style={{ width: '3rem', height: '3rem', background: 'linear-gradient(to right, #8a2be2, #4169e1)' }}
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
            <h1 className="h1 fw-bold text-white">Asistente WhatsApp</h1>
          </div>
          <p className="lead text-light mx-auto" style={{ maxWidth: '40rem' }}>
            Escanea el código QR para activar tu <strong>Asistente Legal Personalizado</strong>
          </p>
        </div>

        <div className="row g-4">
          <div className="col-lg-6">
            <Card className="card p-4 bg-dark text-white border-light shadow">
              <ConnectionStatus
                status={clientData?.whatsapp?.status || 'disconnected'}
                connectedUser={{ name: clientData?.client?.name || 'Desconocido', phone: clientData?.whatsapp?.connected_phone || 'Número desconocido' }}
                messageCount={clientData?.whatsapp?.messageCount || 0}
                pausedCount={clientData?.whatsapp?.pausedCount || 0}
                globalPause={clientData?.whatsapp?.globalPause || false}
              />
              {errorMessage && (
                <div className="alert alert-danger p-3 mt-3">
                  <p className="text-danger mb-0">{errorMessage}</p>
                </div>
              )}
              {clientData?.whatsapp?.connected ? (
                <>
                  <Separator className="my-4 bg-light opacity-25" />
                  <div className="text-center mb-4">
                    <div
                      className="rounded-circle d-flex align-items-center justify-content-center mx-auto bg-success mb-3"
                      style={{ width: '5rem', height: '5rem' }}
                    >
                      <svg className="text-white" style={{ width: '2.5rem', height: '2.5rem' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                    <h3 className="h4 fw-bold text-white">¡Conectado!</h3>
                    <p className="text-light">Tu <strong>Asistente Legal Personalizado</strong> está activo</p>
                    <div className="alert alert-success p-3 mt-3">
                      <p className="text-success fw-semibold mb-1">🏛️ Asistente Jurídico Activo</p>
                      <p className="small text-success mb-0">
                        {clientData.whatsapp.globalPause
                          ? 'El asistente está pausado globalmente. Usa "activar todo" en WhatsApp para reanudar.'
                          : `Responderá automáticamente a TODOS los mensajes de WhatsApp. Conversaciones pausadas: ${clientData.whatsapp.pausedCount || 0}`}
                      </p>
                    </div>
                    <Button
                      onClick={handleDisconnect}
                      className="btn btn-danger mt-3"
                      disabled={refreshing}
                    >
                      {refreshing ? 'Desconectando...' : 'Desconectar WhatsApp'}
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <Separator className="my-4 bg-light opacity-25" />
                  <QRCodeDisplay
                    qrCode={qrCode}
                    status={clientData?.whatsapp?.status || 'disconnected'}
                    errorMessage={clientData?.client?.status === 'pending' ? 'El cliente está en estado pendiente. Escanea el código QR para activar.' : errorMessage}
                  />
                  <div className="text-center mt-3">
                    <Button
                      onClick={handleRefresh}
                      className="btn btn-outline-light"
                      disabled={refreshing}
                    >
                      {refreshing ? 'Verificando...' : 'Actualizar Estado'}
                    </Button>
                  </div>
                </>
              )}
            </Card>
          </div>
          <div className="col-lg-6">
            <AssistantInfo status={clientData?.whatsapp?.status || 'disconnected'} clientStatus={clientData?.client?.status || 'pending'} />
            <Card className="card p-4 bg-dark text-white border-light mb-4">
              <h3 className="h5 fw-bold text-white mb-3">📱 Instrucciones (iPhone)</h3>
              <div className="small text-light mb-3">
                <div className="d-flex align-items-start gap-2 mb-2">
                  <Badge variant="outline" className="badge bg-secondary">
                    1
                  </Badge>
                  <span>Abre WhatsApp en tu iPhone</span>
                </div>
                <div className="d-flex align-items-start gap-2 mb-2">
                  <Badge variant="outline" className="badge bg-secondary">
                    2
                  </Badge>
                  <span>Ve a Configuración → Dispositivos Vinculados</span>
                </div>
                <div className="d-flex align-items-start gap-2 mb-2">
                  <Badge variant="outline" className="badge bg-secondary">
                    3
                  </Badge>
                  <span>Toca "Vincular un dispositivo"</span>
                </div>
                <div className="d-flex align-items-start gap-2 mb-2">
                  <Badge variant="outline" className="badge bg-secondary">
                    4
                  </Badge>
                  <span>Escanea el código QR que aparece arriba</span>
                </div>
                <div className="d-flex align-items-start gap-2 mb-2">
                  <Badge variant="outline" className="badge bg-success">
                    ✅
                  </Badge>
                  <span>
                    <strong>¡LISTO! Cuando te escriban, tu asistente responderá automáticamente</strong>
                  </span>
                </div>
              </div>
              <div className="alert alert-info p-3 mt-3">
                <p className="text-info fw-semibold mb-1">🤖 Asistente Legal Personalizado</p>
                <p className="small text-info mb-0">
                  Una vez conectado, tu asistente legal responderá automáticamente a todas las consultas sin necesidad de tu intervención. Perfecto para atender clientes 24/7.
                </p>
              </div>
            </Card>
            <Card className="card p-4 bg-warning text-dark border-warning">
              <h3 className="h5 fw-bold text-warning mb-2">⚠️ Importante</h3>
              <p className="small text-warning mb-0">
                <strong>Para recibir muchos mensajes diarios:</strong> Una vez conectado, tu asistente procesará TODOS los mensajes automáticamente. No necesitas hacer nada más.
              </p>
              <p className="small text-warning mt-2 mb-0">
                <strong>Pausar el asistente:</strong> Envía "pausar" o "pausar todo" desde tu número registrado en WhatsApp para pausar conversaciones específicas o todas.
              </p>
            </Card>
          </div>
        </div>
      </div>
      <ToastContainer position="top-right" autoClose={3000} />
    </div>
  );
};

export default QRAssistantPage;