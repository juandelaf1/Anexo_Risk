-- Crea la tabla de usuarios para autenticación JWT
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'ciudadano',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Crea la tabla de tokens de refresco
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- Crea la tabla de roles
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Inserta roles por defecto
INSERT OR IGNORE INTO roles (name, description) VALUES
    ('ciudadano', 'Usuario regular'),
    ('organizador', 'Usuario con permisos de organización'),
    ('admin', 'Usuario administrador con todos los permisos');

-- Crea la tabla de permisos
CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Crea la tabla de roles_permissions
CREATE TABLE IF NOT EXISTS roles_permissions (
    role_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions (id) ON DELETE CASCADE
);

-- Crea la tabla de usuarios_roles
CREATE TABLE IF NOT EXISTS users_roles (
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE CASCADE
);

-- Inserta permisos por defecto
INSERT OR IGNORE INTO permissions (name, description) VALUES
    ('create_need', 'Crear necesidades'),
    ('update_need', 'Actualizar necesidades'),
    ('delete_need', 'Eliminar necesidades'),
    ('create_resource', 'Crear recursos'),
    ('update_resource', 'Actualizar recursos'),
    ('delete_resource', 'Eliminar recursos'),
    ('create_organization', 'Crear organizaciones'),
    ('update_organization', 'Actualizar organizaciones'),
    ('delete_organization', 'Eliminar organizaciones'),
    ('create_user', 'Crear usuarios'),
    ('update_user', 'Actualizar usuarios'),
    ('delete_user', 'Eliminar usuarios');

-- Asigna permisos a roles
INSERT OR IGNORE INTO roles_permissions (role_id, permission_id) VALUES
    ((SELECT id FROM roles WHERE name = 'ciudadano'), (SELECT id FROM permissions WHERE name = 'create_need')),
    ((SELECT id FROM roles WHERE name = 'ciudadano'), (SELECT id FROM permissions WHERE name = 'update_need')),
    ((SELECT id FROM roles WHERE name = 'ciudadano'), (SELECT id FROM permissions WHERE name = 'delete_need')),
    ((SELECT id FROM roles WHERE name = 'organizador'), (SELECT id FROM permissions WHERE name = 'create_need')),
    ((SELECT id FROM roles WHERE name = 'organizador'), (SELECT id FROM permissions WHERE name = 'update_need')),
    ((SELECT id FROM roles WHERE name = 'organizador'), (SELECT id FROM permissions WHERE name = 'delete_need')),
    ((SELECT id FROM roles WHERE name = 'organizador'), (SELECT id FROM permissions WHERE name = 'create_resource')),
    ((SELECT id FROM roles WHERE name = 'organizador'), (SELECT id FROM permissions WHERE name = 'update_resource')),
    ((SELECT id FROM roles WHERE name = 'organizador'), (SELECT id FROM permissions WHERE name = 'delete_resource')),
    ((SELECT id FROM roles WHERE name = 'admin'), (SELECT id FROM permissions WHERE name = 'create_need')),
    ((SELECT id FROM roles WHERE name = 'admin'), (SELECT id FROM permissions WHERE name = 'update_need')),
    ((SELECT id FROM roles WHERE name = 'admin'), (SELECT id FROM permissions WHERE name = 'delete_need')),
    ((SELECT id FROM roles WHERE name = 'admin'), (SELECT id FROM permissions WHERE name = 'create_resource')),
    ((SELECT id FROM roles WHERE name = 'admin'), (SELECT id FROM permissions WHERE name = 'update_resource')),
    ((SELECT id FROM roles WHERE name = 'admin'), (SELECT id FROM permissions WHERE name = 'delete_resource')),
    ((SELECT id FROM roles WHERE name = 'admin'), (SELECT id FROM permissions WHERE name = 'create_organization')),
    ((SELECT id FROM roles WHERE name = 'admin'), (SELECT id FROM permissions WHERE name = 'update_organization')),
    ((SELECT id FROM roles WHERE name = 'admin'), (SELECT id FROM permissions WHERE name = 'delete_organization')),
    ((SELECT id FROM roles WHERE name = 'admin'), (SELECT id FROM permissions WHERE name = 'create_user')),
    ((SELECT id FROM roles WHERE name = 'admin'), (SELECT id FROM permissions WHERE name = 'update_user')),
    ((SELECT id FROM roles WHERE name = 'admin'), (SELECT id FROM permissions WHERE name = 'delete_user'));
