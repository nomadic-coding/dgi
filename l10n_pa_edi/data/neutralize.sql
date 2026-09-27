-- Remove HKA credentials and cached JWT from sanitized databases.
UPDATE res_company
   SET hka_usuario = NULL,
       hka_clave = NULL,
       hka_auth_token = NULL,
       hka_auth_token_expiry = NULL;
