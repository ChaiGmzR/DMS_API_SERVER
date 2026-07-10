ALTER TABLE defect_data_smd
  MODIFY etapa_deteccion ENUM('LQC', 'OQC', 'SMD') NOT NULL;
