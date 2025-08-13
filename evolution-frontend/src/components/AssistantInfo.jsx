import React from 'react';
import { Zap, BookOpen, Lock, Clock, Info, Smartphone, Wifi, WifiOff } from 'lucide-react';

const AssistantInfo = ({ status, clientStatus }) => {
  const features = [
    {
      icon: <Zap className="w-6 h-6 text-primary" />,
      title: 'Respuesta Instantánea',
      description: 'Responde en segundos a cualquier consulta',
    },
    {
      icon: <BookOpen className="w-6 h-6 text-primary" />,
      title: 'Conocimiento Amplio',
      description: 'Powered by tu asistente personalizado para respuestas inteligentes',
    },
    {
      icon: <Lock className="w-6 h-6 text-primary" />,
      title: 'Seguro y Privado',
      description: 'Tus conversaciones están protegidas',
    },
    {
      icon: <Clock className="w-6 h-6 text-primary" />,
      title: '24/7 Disponible',
      description: 'Nunca pierdas una consulta de cliente',
    },
  ];

  // Status-specific messaging
  const getStatusMessage = () => {
    if (clientStatus === 'pending') {
      return {
        icon: <Info className="w-4 h-4 me-2" />,
        title: 'Servicio Pendiente',
        message: 'El servicio está en estado pendiente. Escanea el código QR para activarlo.',
        alertClass: 'alert-warning text-yellow-800 bg-yellow-50 border-yellow-200',
      };
    }
    switch (status) {
      case 'connecting':
        return {
          icon: <Smartphone className="w-4 h-4 me-2" />,
          title: 'Listo para Conectar',
          message: 'Escanea el código QR para activar tu asistente y comenzar a responder mensajes automáticamente.',
          alertClass: 'alert-info text-blue-800 bg-blue-50 border-blue-200',
        };
      case 'open':
        return {
          icon: <Wifi className="w-4 h-4 me-2" />,
          title: 'Asistente Activo',
          message: 'Tu asistente está conectado y respondiendo mensajes en WhatsApp 24/7.',
          alertClass: 'alert-success text-green-800 bg-green-50 border-green-200',
        };
      case 'close':
        return {
          icon: <WifiOff className="w-4 h-4 me-2" />,
          title: 'Conexión Cerrada',
          message: 'La conexión a WhatsApp está cerrada. Intenta actualizar el estado o contacta a soporte (contacto@tiks.cl).',
          alertClass: 'alert-danger text-red-800 bg-red-50 border-red-200',
        };
      default:
        return {
          icon: <Info className="w-4 h-4 me-2" />,
          title: 'Personalización',
          message: 'Puedes personalizar las respuestas del asistente para que se adapte a tu negocio y estilo de comunicación.',
          alertClass: 'alert-info text-blue-800 bg-blue-50 border-blue-200',
        };
    }
  };

  const { icon, title, message, alertClass } = getStatusMessage();

  return (
    <div className="card bg-gray-900 text-white border-gray-700 shadow-sm p-4 mx-auto" style={{ maxWidth: '500px' }}>
      <div className="d-flex align-items-center mb-4">
        <div
          className="bg-primary rounded-circle d-flex align-items-center justify-content-center me-3"
          style={{ width: '40px', height: '40px' }}
        >
          <Info className="w-5 h-5 text-white" aria-label="Asistente IA" />
        </div>
        <div>
          <h3 className="h5 fw-bold mb-1">Tu Asistente IA</h3>
          <span className="badge bg-green-100 text-green-800 border border-green-300">
            Asistente Personalizado
          </span>
        </div>
      </div>

      <div className="mb-4">
        {features.map((feature, index) => (
          <div key={index} className="card bg-gray-800 text-white border-gray-600 mb-3 p-3">
            <div className="d-flex align-items-start">
              <div
                className="bg-blue-100 text-blue-800 rounded-circle d-flex align-items-center justify-content-center me-3"
                style={{ width: '32px', height: '32px' }}
              >
                {feature.icon}
              </div>
              <div>
                <h4 className="h6 fw-semibold mb-1">{feature.title}</h4>
                <p className="small text-gray-300 mb-0">{feature.description}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className={`alert ${alertClass}`}>
        <div className="d-flex align-items-center mb-2">
          {icon}
          <span className="small fw-medium">{title}</span>
        </div>
        <p className="small mb-0">{message}</p>
      </div>
    </div>
  );
};

export default AssistantInfo;