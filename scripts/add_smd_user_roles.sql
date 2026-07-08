ALTER TABLE usuarios_dms
  MODIFY rol ENUM(
    'Inspector_LQC',
    'Inspector_OQC',
    'Reparador',
    'Operador_SMD',
    'Supervisor_Calidad',
    'Supervisor_SMD',
    'Supervisor_Produccion',
    'Admin'
  ) NOT NULL;

UPDATE usuarios_dms
SET rol = 'Supervisor_SMD', area = 'SMD'
WHERE username = 'supervisor_smd';
