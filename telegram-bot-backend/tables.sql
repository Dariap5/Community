
CREATE TABLE bot_settings (
	key VARCHAR(120) NOT NULL, 
	value_text TEXT, 
	is_encrypted BOOLEAN NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (key)
)



CREATE TABLE funnels (
	id UUID NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	entry_key VARCHAR(120), 
	is_active BOOLEAN NOT NULL, 
	is_archived BOOLEAN NOT NULL, 
	cross_entry_behavior funnelcrossentrybehavior NOT NULL, 
	notes TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
)



CREATE TABLE products (
	id UUID NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	price NUMERIC(10, 2) NOT NULL, 
	description TEXT, 
	photo_file_id VARCHAR(1024), 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)



CREATE TABLE tracks (
	id UUID NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	config JSONB NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)



CREATE TABLE funnel_steps (
	id UUID NOT NULL, 
	funnel_id UUID NOT NULL, 
	"order" INTEGER NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	step_key VARCHAR(100) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	config JSONB NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_funnel_step_key UNIQUE (funnel_id, step_key), 
	FOREIGN KEY(funnel_id) REFERENCES funnels (id) ON DELETE CASCADE
)



CREATE TABLE users (
	telegram_id BIGSERIAL NOT NULL, 
	username VARCHAR(255), 
	first_name VARCHAR(255), 
	last_name VARCHAR(255), 
	source_deeplink VARCHAR(255), 
	selected_track_id UUID, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	last_activity_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (telegram_id), 
	FOREIGN KEY(selected_track_id) REFERENCES tracks (id) ON DELETE SET NULL
)



CREATE TABLE purchases (
	id UUID NOT NULL, 
	user_id BIGINT NOT NULL, 
	product_id UUID NOT NULL, 
	amount NUMERIC(10, 2) NOT NULL, 
	status paymentstatus NOT NULL, 
	payment_provider_id VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	paid_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (telegram_id) ON DELETE CASCADE, 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE, 
	UNIQUE (payment_provider_id)
)



CREATE TABLE scheduled_tasks (
	id UUID NOT NULL, 
	user_id BIGINT NOT NULL, 
	task_type VARCHAR(100) NOT NULL, 
	payload JSONB NOT NULL, 
	execute_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	status scheduledtaskstatus NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (telegram_id) ON DELETE CASCADE
)



CREATE TABLE user_funnel_state (
	id UUID NOT NULL, 
	user_id BIGINT NOT NULL, 
	funnel_id UUID NOT NULL, 
	current_step_id UUID, 
	status funnelstatus NOT NULL, 
	started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (telegram_id) ON DELETE CASCADE, 
	FOREIGN KEY(funnel_id) REFERENCES funnels (id) ON DELETE CASCADE, 
	FOREIGN KEY(current_step_id) REFERENCES funnel_steps (id) ON DELETE SET NULL
)



CREATE TABLE user_tags (
	user_id BIGINT NOT NULL, 
	tag VARCHAR(128) NOT NULL, 
	assigned_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (user_id, tag), 
	CONSTRAINT uq_user_tags_user_id_tag UNIQUE (user_id, tag), 
	FOREIGN KEY(user_id) REFERENCES users (telegram_id) ON DELETE CASCADE
)


