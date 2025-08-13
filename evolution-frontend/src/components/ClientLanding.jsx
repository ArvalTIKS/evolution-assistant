import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { toast, ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import { Card } from './ui/card';
import { Button } from './ui/button';
import { Separator } from './ui/separator';
import ConnectionStatus from './ConnectionStatus';
import QRCodeDisplay from './QRCodeDisplay';
import AssistantInfo from './AssistantInfo';
import { CheckCircle, XCircle, Smartphone, RefreshCw, Bot, WifiOff, LogOut, AlertTriangle } from 'lucide-react';

const ClientLanding = () => {
  const { unique_url } = useParams();
  const [clientData, setClientData] = useState(null);
  const [qrCode, setQrCode] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const statusTimerRef = useRef(null);
  const qrTimerRef = useRef(null);
  const retryCountRef = useRef(0);
  const maxRetries = 3;

  const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
  const authToken = import.meta.env.VITE_AUTH_TOKEN;

  console.log('ClientLanding initial render:', { unique_url, backendUrl, authToken: !!authToken });

  const fetchClientData = useCallback(async (fetchQr = true) => {
    if (!unique_url) {
      console.error('fetchClientData: unique_url is undefined');
      setErrorMessage('Enlace inválido. Verifica la URL e intenta nuevamente.');
      setLoading(false);
      setRefreshing(false);
      return;
    }

    try {
      console.log('fetchClientData: Fetching client data for', unique_url);
      setErrorMessage(null);
      setLoading(true);

      // Fetch client data from landing endpoint
      const landingResponse = await axios.get(`${backendUrl}/client/${unique_url}/landing`, {
        headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
        timeout: 30000,
      });
      console.log('fetchClientData: Landing response', landingResponse.data);
      const client = landingResponse.data;

      // Fetch status
      const statusResponse = await axios.get(`${backendUrl}/client/${client.id}/status`, {
        headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
        timeout: 30000,
      });
      console.log('fetchClientData: Status response', statusResponse.data);

      const newClientData = {
        client: {
          id: client.id,
          name: client.name,
          email: client.email,
          messageCount: client.messageCount || 0,
          pausedCount: client.pausedCount || 0,
          globalPause: client.globalPause || false,
        },
        whatsapp: {
          connected: client.connected,
          status: statusResponse.data.status,
          connected_phone: client.connected_phone,
        },
      };
      setClientData(newClientData);

      if (statusResponse.data.status !== 'open' && fetchQr) {
        try {
          console.log('fetchClientData: Fetching QR code for', client.id);
          const qrResponse = await axios.get(`${backendUrl}/client/${client.id}/qr`, {
            headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
            timeout: 30000,
          });
          console.log('fetchClientData: QR response', qrResponse.data);
          if (qrResponse.data.qr) {
            setQrCode(qrResponse.data.qr);
            setErrorMessage(null);
            retryCountRef.current = 0;
          } else if (qrResponse.data.state === 'open') {
            setClientData((prevData) => ({
              ...prevData,
              whatsapp: {
                ...prevData.whatsapp,
                connected: true,
                connected_phone: qrResponse.data.connected_phone || null,
                status: 'open',
              },
            }));
            setQrCode(null);
            setErrorMessage(null);
          } else {
            setQrCode(null);
            setErrorMessage(qrResponse.data.error || 'No se pudo cargar el código QR. Intenta de nuevo.');
          }
        } catch (qrError) {
          console.error('fetchClientData: Error fetching QR code:', qrError);
          setQrCode(null);
          const qrErrorMsg = qrError.response?.data?.detail || 'Error al conectar con el servidor para obtener el QR';
          setErrorMessage(qrErrorMsg);
          if (
            qrErrorMsg.includes('Instance') &&
            qrErrorMsg.includes('does not exist') &&
            retryCountRef.current < maxRetries
          ) {
            retryCountRef.current += 1;
            console.log(`fetchClientData: Instance not found, retrying (${retryCountRef.current}/${maxRetries})...`);
            await new Promise((resolve) => setTimeout(resolve, 2000));
            await fetchClientData(fetchQr);
          }
        }
      } else {
        setQrCode(null);
        if (statusResponse.data.status === 'open') {
          setErrorMessage(null);
        }
      }
    } catch (err) {
      console.error('fetchClientData: Error fetching client data:', err);
      setQrCode(null);
      setErrorMessage(
        err.response?.status === 404
          ? 'Cliente no encontrado. Verifica que el enlace sea correcto o contacta a soporte.'
          : err.response?.status === 401
          ? 'Acceso no autorizado. Contacta al administrador.'
          : 'No se pudo conectar con el servidor. Por favor intenta nuevamente.'
      );
      toast.error(err.message || 'Error desconocido al conectar con el servidor.');
    } finally {
      console.log('fetchClientData: Clearing loading state', { clientData, qrCode, errorMessage });
      setLoading(false);
      setRefreshing(false);
    }
  }, [unique_url, authToken, backendUrl]);

  const handleRefresh = async () => {
    console.log('handleRefresh: Triggered');
    setRefreshing(true);
    retryCountRef.current = 0;
    await fetchClientData(true);
    setRefreshing(false);
  };

  const handleDisconnectWhatsApp = async () => {
    if (!clientData?.client?.id) {
      console.error('handleDisconnectWhatsApp: No client ID');
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
    console.log('handleDisconnectWhatsApp: Disconnecting');
    setRefreshing(true);
    try {
      await axios.post(
        `${backendUrl}/admin/clients/${clientData.client.id}/toggle`,
        { action: 'disconnect' },
        {
          headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
          timeout: 30000,
        }
      );
      toast.success('✅ WhatsApp desvinculado exitosamente.');
      await fetchClientData(true);
    } catch (err) {
      console.error('handleDisconnectWhatsApp: Error disconnecting WhatsApp:', err);
      toast.error('Error al desvincular WhatsApp. Por favor intenta nuevamente.');
    } finally {
      setRefreshing(false);
    }
  };

    useEffect(() => {
    console.log('useEffect: Initial load');
    const loadData = async () => {
      try {
        setLoading(true);
        await fetchClientData(true);
      } catch (err) {
        console.error('useEffect: Error in initial load', err);
        setErrorMessage('Error al cargar los datos iniciales. Por favor intenta nuevamente.');
        toast.error('Error al cargar los datos iniciales.');
      } finally {
        console.log('useEffect: Clearing initial loading state', { clientData, qrCode, errorMessage });
        setLoading(false);
      }
    };
    loadData();

    const socket = new WebSocket(`${backendUrl.replace('http', 'ws')}/ws`);

    socket.onopen = () => {
      console.log('WebSocket connected for landing page');
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('WebSocket message received on landing page:', data);

      if (data.clientId === clientData?.client?.id) {
        if (data.qrCode) {
          setQrCode(data.qrCode);
          setErrorMessage(null);
        }
        setClientData((prevData) => ({
          ...prevData,
          whatsapp: {
            ...prevData.whatsapp,
            status: data.status,
            connected: data.status === 'open',
            connected_phone: data.phone || prevData.whatsapp.connected_phone,
          },
        }));
      }
    };

    socket.onclose = () => {
      console.log('WebSocket disconnected from landing page');
    };

    socket.onerror = (error) => {
      console.error('WebSocket error on landing page:', error);
    };

    return () => {
      console.log('useEffect: Cleanup socket');
      socket.close();
    };
  }, [fetchClientData, backendUrl, clientData?.client?.id]);

  if (loading) {
    return (
      <div className="min-vh-100 bg-light d-flex align-items-center justify-content-center">
        <div className="text-center">
          <div className="spinner-border text-primary mb-3" role="status">
            <span className="visually-hidden">Cargando...</span>
          </div>
          <p className="text-dark">Cargando plataforma...</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="min-vh-100 bg-light">
        <div className="container py-5">
          <div className="text-center mb-5">
            <div className="d-flex align-items-center justify-content-center mb-3">
              <Bot className="text-primary me-3" size={48} />
              <div>
                <h1 className="h2 font-bold text-dark">Asistente WhatsApp</h1>
                <p className="h5 text-muted">{clientData?.client?.name || 'Cargando...'}</p>
              </div>
            </div>
          </div>

          {errorMessage && (
            <Card className="shadow-sm mb-4">
              <div className="card-body">
                <div className="alert alert-danger d-flex align-items-center">
                  <AlertTriangle className="me-2 text-danger" size={24} />
                  <div>
                    <p className="fw-medium mb-1">Error</p>
                    <p className="mb-2 small">{errorMessage}</p>
                    <Button
                      onClick={handleRefresh}
                      disabled={refreshing}
                      className="btn btn-outline-primary btn-sm"
                    >
                      {refreshing ? (
                        <>
                          <RefreshCw className="animate-spin me-2" size={16} />
                          Intentando de nuevo...
                        </>
                      ) : (
                        <>
                          <RefreshCw className="me-2" size={16} />
                          Intentar de nuevo
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              </div>
            </Card>
          )}

          <div className="row g-4">
            <div className="col-lg-6">
              <Card className="shadow-sm mb-5">
                <div className="card-header d-flex align-items-center justify-content-between">
                  <h2 className="h5 mb-0 text-dark">Estado del Asistente</h2>
                  <Button
                    onClick={handleRefresh}
                    disabled={refreshing}
                    className="btn btn-link text-muted p-0"
                  >
                    <RefreshCw className={refreshing ? 'animate-spin' : ''} size={20} />
                  </Button>
                </div>
                <div className="card-body">
                  <ConnectionStatus
                    status={clientData?.whatsapp?.status || 'disconnected'}
                    connectedUser={{ name: clientData?.client?.name || 'Desconocido', phone: clientData?.whatsapp?.connected_phone || 'Número desconocido' }}
                    messageCount={clientData?.client?.messageCount || 0}
                    pausedCount={clientData?.client?.pausedCount || 0}
                    globalPause={clientData?.client?.globalPause || false}
                  />
                  {clientData?.whatsapp?.connected || clientData?.whatsapp?.status === 'open' ? (
                    <div className="alert alert-success d-flex align-items-center">
                      <CheckCircle className="me-2" size={20} />
                      <div>
                        <p className="fw-medium mb-1">¡Tu asistente está activo!</p>
                        <p className="mb-0 small">
                          Los usuarios pueden enviar mensajes a tu WhatsApp y recibirán respuestas automáticas.
                        </p>
                      </div>
                    </div>
                  ) : clientData?.whatsapp?.status === 'connecting' ? (
                    <div className="alert alert-warning d-flex align-items-center">
                      <Smartphone className="me-2" size={20} />
                      <div>
                        <p className="fw-medium mb-1">Conectando WhatsApp</p>
                        <p className="mb-0 small">Escanea el código QR para completar la conexión.</p>
                      </div>
                    </div>
                  ) : clientData?.whatsapp?.status === 'close' ? (
                    <div className="alert alert-danger d-flex align-items-center">
                      <WifiOff className="me-2" size={20} />
                      <div>
                        <p className="fw-medium mb-1">Conexión cerrada</p>
                        <p className="mb-0 small">La conexión a WhatsApp está cerrada. Intenta actualizar el estado.</p>
                      </div>
                    </div>
                  ) : (
                    <div className="alert alert-warning d-flex align-items-center">
                      <Smartphone className="me-2" size={20} />
                      <div>
                        <p className="fw-medium mb-1">Listo para conectar WhatsApp</p>
                        <p className="mb-0 small">Escanea el código QR para activar tu asistente.</p>
                      </div>
                    </div>
                  )}
                </div>
              </Card>

              {!(clientData?.whatsapp?.connected || clientData?.whatsapp?.status === 'open') && (
                <Card className="shadow-sm">
                  <div className="card-body">
                    <QRCodeDisplay
                      qrCode={qrCode}
                      status={clientData?.whatsapp?.status || 'disconnected'}
                      errorMessage={null} // Error message is now handled above
                    />
                  </div>
                </Card>
              )}

              {(clientData?.whatsapp?.connected || clientData?.whatsapp?.status === 'open') && (
                <Card className="shadow-sm">
                  <div className="card-body text-center">
                    <CheckCircle className="text-success mb-3" size={48} />
                    <h4 className="h5 font-bold text-dark mb-2">¡WhatsApp Conectado!</h4>
                    <p className="text-muted mb-4">
                      Tu asistente está funcionando y listo para atender mensajes automáticamente.
                    </p>
                    <Button
                      onClick={handleDisconnectWhatsApp}
                      disabled={refreshing || !clientData?.client?.id}
                      className="btn btn-danger d-flex align-items-center mx-auto"
                    >
                      <LogOut className="me-2" size={16} />
                      {refreshing ? 'Desvinculando...' : 'Desvincular WhatsApp'}
                    </Button>
                    <div className="alert alert-warning mt-4">
                      <p className="mb-0 small">
                        <strong>Nota:</strong> Al desvincular, el dispositivo se eliminará de tu lista de
                        "Dispositivos vinculados" en WhatsApp y necesitarás escanear un nuevo código QR.
                      </p>
                    </div>
                  </div>
                </Card>
              )}
            </div>

            <div className="col-lg-6">
              <AssistantInfo status={clientData?.whatsapp?.status || 'disconnected'} />
              <Card className="shadow-sm mt-4">
                <div className="card-body">
                  <h3 className="h5 fw-bold text-dark mb-3">📱 Instrucciones para Conectar</h3>
                  <div className="small text-muted mb-3">
                    <div className="d-flex align-items-start gap-2 mb-2">
                      <span className="badge bg-secondary">1</span>
                      <span>Abre WhatsApp en tu teléfono</span>
                    </div>
                    <div className="d-flex align-items-start gap-2 mb-2">
                      <span className="badge bg-secondary">2</span>
                      <span>Ve a Menú → Dispositivos vinculados</span>
                    </div>
                    <div className="d-flex align-items-start gap-2 mb-2">
                      <span className="badge bg-secondary">3</span>
                      <span>Toca "Vincular un dispositivo"</span>
                    </div>
                    <div className="d-flex align-items-start gap-2 mb-2">
                      <span className="badge bg-secondary">4</span>
                      <span>Escanea el código QR</span>
                    </div>
                    <div className="d-flex align-items-start gap-2 mb-2">
                      <span className="badge bg-success">✅</span>
                      <span>
                        <strong>¡Listo! Tu asistente responderá automáticamente a los mensajes</strong>
                      </span>
                    </div>
                  </div>
                  <div className="alert alert-info p-3 mt-3">
                    <p className="text-info fw-semibold mb-1">🤖 Asistente Personalizado</p>
                    <p className="small text-info mb-0">
                      Una vez conectado, tu asistente responderá automáticamente a todas las consultas 24/7.
                    </p>
                  </div>
                </div>
              </Card>
            </div>
          </div>

          <div className="text-center mt-5">
            <p className="text-muted small">
              ¿Necesitas ayuda? Contacta:{' '}
              <a href="mailto:contacto@tiks.cl" className="text-primary">
                contacto@tiks.cl
              </a>
            </p>
          </div>
        </div>
      </div>
      <ToastContainer position="top-right" autoClose={3000} />
    </>
  );
};

export default ClientLanding;