import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import {
  AlertCircle,
  CheckCircle,
  User,
  Mail,
  Bot,
  Trash2,
  Power,
  PowerOff,
  Plus,
  Edit,
  Send,
  MessageSquare,
  List,
  Key,
} from 'lucide-react';
import 'bootstrap/dist/css/bootstrap.min.css';

const AdminPanel = () => {
  // State Management
  const [clients, setClients] = useState([]);
  const [loadingStates, setLoadingStates] = useState({});
  const [error, setError] = useState(null);
  const [formError, setFormError] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [showEditEmailForm, setShowEditEmailForm] = useState(false);
  const [showChats, setShowChats] = useState(null);
  const [showQR, setShowQR] = useState(null);
  const [showThreads, setShowThreads] = useState(null);
  const [editingClient, setEditingClient] = useState(null);
  const [newEmail, setNewEmail] = useState('');
  const [chats, setChats] = useState([]);
  const [threads, setThreads] = useState([]);
  const [qrData, setQrData] = useState({ qr: null, error: null });
  const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

  // Debounce Utility
  const useDebounce = (fn, delay) => {
    const timeoutRef = useRef(null);
    const debouncedFn = useCallback(
      (...args) => {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = setTimeout(() => fn(...args), delay);
      },
      [fn, delay]
    );
    useEffect(() => {
      return () => clearTimeout(timeoutRef.current);
    }, []);
    return debouncedFn;
  };

  // API Functions with Retry Logic
  const fetchWithRetry = async (url, options = {}, retries = 3, delay = 1000) => {
    for (let i = 0; i < retries; i++) {
      try {
        const response = await axios(url, options);
        return response;
      } catch (error) {
        if (i < retries - 1 && error.code === 'ERR_NETWORK') {
          await new Promise((resolve) => setTimeout(resolve, delay));
          continue;
        }
        throw error;
      }
    }
  };

  const fetchClients = useCallback(async () => {
    setLoadingStates((prev) => ({ ...prev, fetchClients: true }));
    setError(null);
    try {
      const response = await fetchWithRetry(`${backendUrl}/admin/clients`);
      const clientsData = Array.isArray(response.data) ? response.data : [];
      // Map id to instance_id and include all client fields
      const mappedClients = clientsData.map((client) => ({
        ...client,
        instance_id: client.id,
      }));
      setClients(mappedClients);
    } catch (error) {
      console.error('Error fetching clients:', error);
      setError(error.response?.data?.detail || 'No se pudieron cargar los clientes');
    } finally {
      setLoadingStates((prev) => ({ ...prev, fetchClients: false }));
    }
  }, [backendUrl]);

  const fetchChats = useCallback(async (instance_id) => {
    setLoadingStates((prev) => ({ ...prev, [`fetchChats-${instance_id}`]: true }));
    setError(null);
    try {
      const response = await fetchWithRetry(`${backendUrl}/admin/chats/${instance_id}`);
      setChats(response.data || []);
      setShowChats(instance_id);
    } catch (error) {
      console.error('Error fetching chats:', error);
      setError(error.response?.data?.detail || 'No se pudo cargar el historial de chats');
    } finally {
      setLoadingStates((prev) => ({ ...prev, [`fetchChats-${instance_id}`]: false }));
    }
  }, [backendUrl]);

  const fetchThreads = useCallback(async (instance_id) => {
    setLoadingStates((prev) => ({ ...prev, [`fetchThreads-${instance_id}`]: true }));
    setError(null);
    try {
      const response = await fetchWithRetry(`${backendUrl}/admin/clients/${instance_id}/threads`);
      setThreads(response.data || []);
      setShowThreads(instance_id);
    } catch (error) {
      console.error('Error fetching threads:', error);
      setError(error.response?.data?.detail || 'No se pudo cargar los hilos');
    } finally {
      setLoadingStates((prev) => ({ ...prev, [`fetchThreads-${instance_id}`]: false }));
    }
  }, [backendUrl]);

  const fetchQR = useCallback(async (instance_id) => {
    setLoadingStates((prev) => ({ ...prev, [`fetchQR-${instance_id}`]: true }));
    setError(null);
    try {
      const response = await fetchWithRetry(`${backendUrl}/client/${instance_id}/qr`);
      setQrData({ qr: response.data.qr, error: response.data.error });
      setShowQR(instance_id);
    } catch (error) {
      console.error('Error fetching QR:', error);
      const errorDetail = error.response?.data?.detail || 'No se pudo cargar el código QR';
      setError(errorDetail);
      setQrData({ qr: null, error: errorDetail });
    } finally {
      setLoadingStates((prev) => ({ ...prev, [`fetchQR-${instance_id}`]: false }));
    }
  }, [backendUrl]);

  const validateForm = () => {
    if (!formData.email.match(/^[\w-.]+@([\w-]+\.)+[\w-]{2,4}$/)) {
      setFormError('Por favor, ingrese un correo electrónico válido');
      return false;
    }
    if (formData.name.length < 3) {
      setFormError('El nombre debe tener al menos 3 caracteres');
      return false;
    }
    if (!formData.openai_api_key) {
      setFormError('La clave de API de OpenAI es requerida');
      return false;
    }
    if (!formData.openai_assistant_id) {
      setFormError('El ID del asistente de OpenAI es requerido');
      return false;
    }
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError(null);
    if (!validateForm()) return;
    setLoadingStates((prev) => ({ ...prev, createClient: true }));
    try {
      await fetchWithRetry(`${backendUrl}/admin/clients`, {
        method: 'POST',
        data: formData,
      });
      setFormData({ name: '', email: '', openai_api_key: '', openai_assistant_id: '' });
      setShowAddForm(false);
      await fetchClients();
      setSuccessMessage('Cliente creado exitosamente! Email enviado.');
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (error) {
      console.error('Error creating client:', error);
      const errorDetail =
        error.response?.data?.detail ||
        'Error al crear el cliente. Por favor, verifica los datos e intenta de nuevo.';
      setFormError(errorDetail);
    } finally {
      setLoadingStates((prev) => ({ ...prev, createClient: false }));
    }
  };

  const toggleClient = async (instance_id, is_active) => {
    setLoadingStates((prev) => ({ ...prev, [`toggle-${instance_id}`]: true }));
    setError(null);
    try {
      await fetchWithRetry(`${backendUrl}/admin/clients/${instance_id}/toggle`, {
        method: 'POST',
        data: { action: is_active ? 'connect' : 'disconnect' },
      });
      await fetchClients();
      setSuccessMessage(`Cliente ${is_active ? 'activado' : 'desactivado'} exitosamente!`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (error) {
      console.error(`Error toggling client:`, error);
      setError(error.response?.data?.detail || `No se pudo ${is_active ? 'activar' : 'desactivar'} el cliente`);
      await fetchClients();
    } finally {
      setLoadingStates((prev) => ({ ...prev, [`toggle-${instance_id}`]: false }));
    }
  };

  const deleteClient = async (instance_id, clientName) => {
    if (!window.confirm(`¿Estás seguro de eliminar al cliente "${clientName}"? Esta acción no se puede deshacer.`)) return;
    setLoadingStates((prev) => ({ ...prev, [`delete-${instance_id}`]: true }));
    setError(null);
    try {
      await fetchWithRetry(`${backendUrl}/admin/clients/${instance_id}`, { method: 'DELETE' });
      setClients((prevClients) => prevClients.filter((client) => client.instance_id !== instance_id));
      setSuccessMessage('Cliente eliminado exitosamente!');
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (error) {
      console.error('Error deleting client:', error);
      setError(error.response?.data?.detail || 'No se pudo eliminar el cliente');
      await fetchClients();
    } finally {
      setLoadingStates((prev) => ({ ...prev, [`delete-${instance_id}`]: false }));
    }
  };

  const updateClientEmail = async (e) => {
    e.preventDefault();
    if (!editingClient || !newEmail.match(/^[\w-.]+@([\w-]+\.)+[\w-]{2,4}$/)) {
      setError('Por favor, ingrese un correo electrónico válido');
      return;
    }
    setLoadingStates((prev) => ({ ...prev, [`updateEmail-${editingClient.instance_id}`]: true }));
    setError(null);
    try {
      await fetchWithRetry(`${backendUrl}/admin/clients/${editingClient.instance_id}/email`, {
        method: 'PUT',
        data: { new_email: newEmail },
      });
      setShowEditEmailForm(false);
      setEditingClient(null);
      setNewEmail('');
      await fetchClients();
      setSuccessMessage('Email actualizado exitosamente!');
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (error) {
      console.error('Error updating email:', error);
      setError(error.response?.data?.detail || 'No se pudo actualizar el email');
    } finally {
      setLoadingStates((prev) => ({ ...prev, [`updateEmail-${editingClient.instance_id}`]: false }));
    }
  };

  const resendEmail = async (instance_id, clientEmail) => {
    if (!window.confirm(`¿Reenviar email de invitación a ${clientEmail}?`)) return;
    setLoadingStates((prev) => ({ ...prev, [`resendEmail-${instance_id}`]: true }));
    setError(null);
    try {
      await fetchWithRetry(`${backendUrl}/admin/clients/${instance_id}/resend-email`, { method: 'POST' });
      setSuccessMessage(`Email reenviado exitosamente a ${clientEmail}`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (error) {
      console.error('Error resending email:', error);
      setError(error.response?.data?.detail || 'No se pudo reenviar el email');
    } finally {
      setLoadingStates((prev) => ({ ...prev, [`resendEmail-${instance_id}`]: false }));
    }
  };

  // Debounced Functions
  const debouncedFetchChats = useDebounce(fetchChats, 300);
  const debouncedFetchThreads = useDebounce(fetchThreads, 300);
  const debouncedFetchQR = useDebounce(fetchQR, 300);
  const debouncedToggleClient = useDebounce(toggleClient, 300);
  const debouncedDeleteClient = useDebounce(deleteClient, 300);
  const debouncedResendEmail = useDebounce(resendEmail, 300);

  // Utility Functions
  const openEditEmailForm = (client) => {
    setEditingClient(client);
    setNewEmail(client.email);
    setShowEditEmailForm(true);
  };

  const getStatusVariant = useCallback((status) => {
    switch (status) {
      case 'open':
      case 'active':
        return 'bg-success text-white';
      case 'close':
      case 'inactive':
        return 'bg-danger text-white';
      case 'connecting':
      case 'awaiting_scan':
        return 'bg-warning text-dark';
      default:
        return 'bg-secondary text-white';
    }
  }, []);

  const getStatusIcon = useCallback((status) => {
    switch (status) {
      case 'open':
      case 'active':
        return <CheckCircle className="me-1" size={16} />;
      case 'close':
      case 'inactive':
        return <PowerOff className="me-1" size={16} />;
      default:
        return <AlertCircle className="me-1" size={16} />;
    }
  }, []);

  // WebSocket Integration
  useEffect(() => {
    const socket = new WebSocket(`${backendUrl.replace('http', 'ws')}/ws`);

    socket.onopen = () => {
      console.log('WebSocket connected');
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('WebSocket message received:', data);
      setClients((prevClients) =>
        prevClients.map((client) =>
          client.instance_id === data.clientId
            ? {
                ...client,
                status: data.status,
                connected_phone: data.phone,
              }
            : client
        )
      );
    };

    socket.onclose = () => {
      console.log('WebSocket disconnected');
    };

    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    return () => {
      socket.close();
    };
  }, [backendUrl]);

  // Remove fetchClientStatus polling since /admin/clients provides status
  useEffect(() => {
    fetchClients();
  }, [fetchClients]);

  // Polling for chats and threads when modals are open
  useEffect(() => {
    if (showChats) {
      fetchChats(showChats);
      const chatPollInterval = setInterval(() => fetchChats(showChats), 5000);
      return () => clearInterval(chatPollInterval);
    }
  }, [showChats, fetchChats]);

  useEffect(() => {
    if (showThreads) {
      fetchThreads(showThreads);
      const threadPollInterval = setInterval(() => fetchThreads(showThreads), 5000);
      return () => clearInterval(threadPollInterval);
    }
  }, [showThreads, fetchThreads]);

  // Render Error State
  if (error && !loadingStates.fetchClients) {
    return (
      <div className="d-flex justify-content-center align-items-center min-vh-100 bg-light">
        <div className="alert alert-danger d-flex align-items-center">
          <AlertCircle className="me-2" size={24} />
          {error}
          <button className="btn btn-primary ms-3" onClick={fetchClients}>
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  // Render Loading State
  if (loadingStates.fetchClients && !clients.length) {
    return (
      <div className="d-flex justify-content-center align-items-center min-vh-100 bg-light">
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">Cargando...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="container-fluid py-4 bg-light min-vh-100">
      {successMessage && (
        <div className="alert alert-success alert-dismissible fade show" role="alert">
          {successMessage}
          <button type="button" className="btn-close" onClick={() => setSuccessMessage(null)}></button>
        </div>
      )}

      <div className="card shadow-sm mb-4">
        <div className="card-header py-3">
          <div className="d-flex align-items-center justify-content-between">
            <div className="d-flex align-items-center">
              <Bot className="text-primary me-3" size={32} />
              <div>
                <h1 className="h2 mb-0">Panel de Administración</h1>
                <p className="text-muted mb-0">Plataforma WhatsApp Multi-Tenant</p>
              </div>
            </div>
            <div>
              <button
                onClick={() => setShowAddForm(true)}
                className="btn btn-primary d-flex align-items-center me-2"
                disabled={loadingStates.createClient}
              >
                {loadingStates.createClient ? (
                  <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                ) : (
                  <Plus className="me-2" size={20} />
                )}
                Agregar Cliente
              </button>
              <button
                onClick={fetchClients}
                className="btn btn-outline-secondary"
                disabled={loadingStates.fetchClients}
              >
                Refrescar Lista
              </button>
            </div>
          </div>
        </div>

        <div className="card-body">
          <div className="row g-4">
            <div className="col-12 col-md-4">
              <div className="card bg-primary-subtle border-0">
                <div className="card-body">
                  <h3 className="fw-bold text-primary mb-0">{clients.length}</h3>
                  <p className="text-muted mb-0">Total Clientes</p>
                </div>
              </div>
            </div>
            <div className="col-12 col-md-4">
              <div className="card bg-success-subtle border-0">
                <div className="card-body">
                  <h3 className="fw-bold text-success mb-0">{clients.filter((c) => c.status === 'open' || c.status === 'active').length}</h3>
                  <p className="text-muted mb-0">Clientes Conectados</p>
                </div>
              </div>
            </div>
            <div className="col-12 col-md-4">
              <div className="card bg-warning-subtle border-0">
                <div className="card-body">
                  <h3 className="fw-bold text-warning mb-0">{clients.filter((c) => c.connected_phone).length}</h3>
                  <p className="text-muted mb-0">WhatsApp Conectados</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {showAddForm && (
        <div className="modal fade show d-block" tabIndex="-1" role="dialog">
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">Agregar Nuevo Cliente</h5>
                <button type="button" className="btn-close" onClick={() => setShowAddForm(false)} aria-label="Close"></button>
              </div>
              <form onSubmit={handleSubmit} className="modal-body">
                {formError && (
                  <div className="alert alert-danger alert-dismissible fade show" role="alert">
                    {formError}
                    <button type="button" className="btn-close" onClick={() => setFormError(null)}></button>
                  </div>
                )}
                <div className="mb-3">
                  <label htmlFor="clientName" className="form-label">Nombre del Cliente</label>
                  <div className="input-group">
                    <span className="input-group-text">
                      <User size={20} />
                    </span>
                    <input
                      type="text"
                      required
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      className="form-control"
                      placeholder="Ej: Bufete Legal XYZ"
                      id="clientName"
                    />
                  </div>
                </div>
                <div className="mb-3">
                  <label htmlFor="clientEmail" className="form-label">Email del Cliente</label>
                  <div className="input-group">
                    <span className="input-group-text">
                      <Mail size={20} />
                    </span>
                    <input
                      type="email"
                      required
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      className="form-control"
                      placeholder="cliente@empresa.com"
                      id="clientEmail"
                    />
                  </div>
                </div>
                <div className="mb-3">
                  <label htmlFor="openaiApiKey" className="form-label">Clave de API de OpenAI</label>
                  <div className="input-group">
                    <span className="input-group-text">
                      <Key size={20} />
                    </span>
                    <input
                      type="text"
                      required
                      value={formData.openai_api_key}
                      onChange={(e) => setFormData({ ...formData, openai_api_key: e.target.value })}
                      className="form-control"
                      placeholder="sk-..."
                      id="openaiApiKey"
                    />
                  </div>
                </div>
                <div className="mb-3">
                  <label htmlFor="openaiAssistantId" className="form-label">ID del Asistente de OpenAI</label>
                  <div className="input-group">
                    <span className="input-group-text">
                      <Bot size={20} />
                    </span>
                    <input
                      type="text"
                      required
                      value={formData.openai_assistant_id}
                      onChange={(e) => setFormData({ ...formData, openai_assistant_id: e.target.value })}
                      className="form-control"
                      placeholder="asst_..."
                      id="openaiAssistantId"
                    />
                  </div>
                </div>
                <div className="d-flex justify-content-end pt-3">
                  <button type="button" className="btn btn-secondary me-2" onClick={() => setShowAddForm(false)}>
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    disabled={loadingStates.createClient}
                    className="btn btn-primary d-flex align-items-center"
                  >
                    {loadingStates.createClient && (
                      <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                    )}
                    Crear y Enviar Email
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {showEditEmailForm && editingClient && (
        <div className="modal fade show d-block" tabIndex="-1" role="dialog">
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">Actualizar Email</h5>
                <button type="button" className="btn-close" onClick={() => setShowEditEmailForm(false)} aria-label="Close"></button>
              </div>
              <div className="modal-body">
                <div className="alert alert-info mb-3">
                  <p className="mb-0">
                    <strong>Cliente:</strong> {editingClient.name}
                    <br />
                    <strong>Email actual:</strong> {editingClient.email}
                  </p>
                </div>
                <form onSubmit={updateClientEmail}>
                  <div className="mb-3">
                    <label htmlFor="newEmail" className="form-label">Nuevo Email</label>
                    <div className="input-group">
                      <span className="input-group-text">
                        <Mail size={20} />
                      </span>
                      <input
                        type="email"
                        required
                        value={newEmail}
                        onChange={(e) => setNewEmail(e.target.value)}
                        className="form-control"
                        placeholder="nuevo@email.com"
                        id="newEmail"
                      />
                    </div>
                  </div>
                  <div className="d-flex justify-content-end pt-3">
                    <button type="button" className="btn btn-secondary me-2" onClick={() => setShowEditEmailForm(false)}>
                      Cancelar
                    </button>
                    <button
                      type="submit"
                      disabled={loadingStates[`updateEmail-${editingClient.instance_id}`]}
                      className="btn btn-primary d-flex align-items-center"
                    >
                      {loadingStates[`updateEmail-${editingClient.instance_id}`] && (
                        <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                      )}
                      Actualizar Email
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </div>
      )}

      {showChats && (
        <div className="modal fade show d-block" tabIndex="-1" role="dialog">
          <div className="modal-dialog modal-dialog-centered modal-lg">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">Historial de Chats</h5>
                <button type="button" className="btn-close" onClick={() => setShowChats(null)} aria-label="Close"></button>
              </div>
              <div className="modal-body" style={{ maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' }}>
                {chats.length === 0 ? (
                  <p className="text-muted text-center">No hay mensajes disponibles. Los chats se capturan en tiempo real.</p>
                ) : (
                  chats.map((msg, i) => (
                    <div
                      key={msg.id || i}
                      className={`p-2 mb-2 rounded ${!msg.is_from_ai ? 'bg-primary-subtle text-start' : 'bg-light text-end'}`}
                    >
                      <p className="mb-0 small">
                        <strong>{!msg.is_from_ai ? 'Usuario' : 'Bot'}</strong>: {msg.message}
                        <span className="text-muted ms-2 small">({new Date(msg.timestamp).toLocaleString()})</span>
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {showThreads && (
        <div className="modal fade show d-block" tabIndex="-1" role="dialog">
          <div className="modal-dialog modal-dialog-centered modal-lg">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">Hilos de Asistente</h5>
                <button type="button" className="btn-close" onClick={() => setShowThreads(null)} aria-label="Close"></button>
              </div>
              <div className="modal-body" style={{ maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' }}>
                {threads.length === 0 ? (
                  <p className="text-muted text-center">No hay hilos disponibles.</p>
                ) : (
                  <table className="table table-striped">
                    <thead>
                      <tr>
                        <th>Teléfono</th>
                        <th>ID del Hilo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {threads.map((thread, i) => (
                        <tr key={i}>
                          <td>{thread.phone_number}</td>
                          <td>{thread.thread_id}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {showQR && (
        <div className="modal fade show d-block" tabIndex="-1" role="dialog">
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">Código QR</h5>
                <button type="button" className="btn-close" onClick={() => setShowQR(null)} aria-label="Close"></button>
              </div>
              <div className="modal-body text-center">
                {qrData.qr ? (
                  <img src={qrData.qr} alt="QR Code" className="img-fluid mx-auto d-block" />
                ) : (
                  <p className="text-danger">{qrData.error || 'No se pudo cargar el código QR'}</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="card shadow-sm">
        <div className="card-header">
          <h2 className="h5 mb-0">Clientes Registrados</h2>
        </div>
        {clients.length === 0 ? (
          <div className="card-body text-center text-muted">
            <Bot className="mb-3" size={48} />
            <p>No hay clientes registrados aún.</p>
            <p className="small">Agrega tu primer cliente usando el botón de arriba.</p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="table table-striped table-hover">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Email</th>
                  <th>WhatsApp</th>
                  <th>Estado</th>
                  <th>ID de Instancia</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((client) => (
                  <tr key={client.instance_id}>
                    <td className="fw-medium">{client.name}</td>
                    <td>{client.email}</td>
                    <td>
                      {client.connected_phone ? (
                        <span className="text-success">{client.connected_phone}</span>
                      ) : (
                        <span className="text-muted">No conectado</span>
                      )}
                    </td>
                    <td>
                      <span className={`badge ${getStatusVariant(client.status)}`}>
                        {getStatusIcon(client.status)}
                        {client.status.charAt(0).toUpperCase() + client.status.slice(1)}
                      </span>
                    </td>
                    <td>
                      <a href={`${backendUrl}/client/${client.unique_url}/landing`} target="_blank" rel="noopener noreferrer">
                        {client.unique_url}
                      </a>
                    </td>
                    <td>
                      <div className="d-flex flex-wrap gap-2">
                        {client.status === 'open' || client.status === 'active' ? (
                          <button
                            onClick={() => debouncedToggleClient(client.instance_id, false)}
                            disabled={loadingStates[`toggle-${client.instance_id}`]}
                            className="btn btn-sm btn-danger d-flex align-items-center shadow-sm"
                          >
                            {loadingStates[`toggle-${client.instance_id}`] ? (
                              <span className="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>
                            ) : (
                              <PowerOff className="me-1" size={16} />
                            )}
                            {loadingStates[`toggle-${client.instance_id}`] ? 'Procesando...' : 'Desactivar'}
                          </button>
                        ) : (
                          <button
                            onClick={() => debouncedToggleClient(client.instance_id, true)}
                            disabled={loadingStates[`toggle-${client.instance_id}`]}
                            className="btn btn-sm btn-success d-flex align-items-center"
                          >
                            {loadingStates[`toggle-${client.instance_id}`] ? (
                              <span className="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>
                            ) : (
                              <Power className="me-1" size={16} />
                            )}
                            {loadingStates[`toggle-${client.instance_id}`] ? 'Procesando...' : 'Activar'}
                          </button>
                        )}
                        <button
                          onClick={() => debouncedFetchChats(client.instance_id)}
                          disabled={loadingStates[`fetchChats-${client.instance_id}`]}
                          className="btn btn-sm btn-outline-primary d-flex align-items-center"
                        >
                          {loadingStates[`fetchChats-${client.instance_id}`] ? (
                            <span className="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>
                          ) : (
                            <MessageSquare className="me-1" size={16} />
                          )}
                          Ver Chats
                        </button>
                        <button
                          onClick={() => debouncedFetchThreads(client.instance_id)}
                          disabled={loadingStates[`fetchThreads-${client.instance_id}`]}
                          className="btn btn-sm btn-outline-info d-flex align-items-center"
                        >
                          {loadingStates[`fetchThreads-${client.instance_id}`] ? (
                            <span className="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>
                          ) : (
                            <List className="me-1" size={16} />
                          )}
                          Ver Hilos
                        </button>
                        <button
                          onClick={() => debouncedFetchQR(client.instance_id)}
                          disabled={loadingStates[`fetchQR-${client.instance_id}`]}
                          className="btn btn-sm btn-outline-primary d-flex align-items-center"
                        >
                          {loadingStates[`fetchQR-${client.instance_id}`] ? (
                            <span className="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>
                          ) : (
                            <Bot className="me-1" size={16} />
                          )}
                          Ver QR
                        </button>
                        <button
                          onClick={() => openEditEmailForm(client)}
                          disabled={loadingStates[`updateEmail-${client.instance_id}`]}
                          className="btn btn-sm btn-warning d-flex align-items-center shadow-sm"
                        >
                          <Edit className="me-1" size={16} />
                          Editar Email
                        </button>
                        <button
                          onClick={() => debouncedResendEmail(client.instance_id, client.email)}
                          disabled={loadingStates[`resendEmail-${client.instance_id}`]}
                          className="btn btn-sm btn-outline-info d-flex align-items-center"
                        >
                          <Send className="me-1" size={16} />
                          Reenviar Email
                        </button>
                        <button
                          onClick={() => debouncedDeleteClient(client.instance_id, client.name)}
                          disabled={loadingStates[`delete-${client.instance_id}`]}
                          className="btn btn-sm btn-danger d-flex align-items-center shadow-sm"
                        >
                          <Trash2 className="me-1" size={16} />
                          Eliminar
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminPanel;