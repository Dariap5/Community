"""initial schema

Revision ID: 001
Revises: 
Create Date: 2026-04-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Create ENUM types
    sa.Enum('allow', 'deny', name='funnelcrossentrybehavior').create(op.get_bind())
    sa.Enum('active', 'paused', 'completed', name='funnelstatus').create(op.get_bind())
    sa.Enum('pending', 'paid', 'failed', 'refunded', name='paymentstatus').create(op.get_bind())
    sa.Enum('pending', 'processing', 'done', 'canceled', 'failed', name='scheduledtaskstatus').create(op.get_bind())

    op.create_table('bot_settings',
        sa.Column('key', sa.String(length=120), nullable=False),
        sa.Column('value_text', sa.Text(), nullable=True),
        sa.Column('is_encrypted', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('key')
    )
    
    op.create_table('funnels',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('entry_key', sa.String(length=120), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_archived', sa.Boolean(), nullable=False),
        sa.Column('cross_entry_behavior', postgresql.ENUM('allow', 'deny', name='funnelcrossentrybehavior', create_type=False), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_funnels_entry_key'), 'funnels', ['entry_key'], unique=True)
    
    op.create_table('products',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('photo_file_id', sa.String(length=1024), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('tracks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create funnel_steps BEFORE users to resolve foreign keys properly
    op.create_table('funnel_steps',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('funnel_id', sa.UUID(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('step_key', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['funnel_id'], ['funnels.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('funnel_id', 'step_key', name='uq_funnel_step_key')
    )
    op.create_index('ix_funnel_steps_funnel_order', 'funnel_steps', ['funnel_id', 'order'], unique=False)
    
    op.create_table('users',
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('first_name', sa.String(length=255), nullable=True),
        sa.Column('last_name', sa.String(length=255), nullable=True),
        sa.Column('source_deeplink', sa.String(length=255), nullable=True),
        sa.Column('selected_track_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_activity_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['selected_track_id'], ['tracks.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('telegram_id')
    )
    op.create_index(op.f('ix_users_source_deeplink'), 'users', ['source_deeplink'], unique=False)
    
    op.create_table('purchases',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('product_id', sa.UUID(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'paid', 'failed', 'refunded', name='paymentstatus', create_type=False), nullable=False),
        sa.Column('payment_provider_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('payment_provider_id')
    )
    op.create_index(op.f('ix_purchases_product_id'), 'purchases', ['product_id'], unique=False)
    op.create_index(op.f('ix_purchases_user_id'), 'purchases', ['user_id'], unique=False)
    
    op.create_table('scheduled_tasks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('task_type', sa.String(length=100), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('execute_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'processing', 'done', 'canceled', 'failed', name='scheduledtaskstatus', create_type=False), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scheduled_tasks_user_id'), 'scheduled_tasks', ['user_id'], unique=False)
    
    op.create_table('user_funnel_state',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('funnel_id', sa.UUID(), nullable=False),
        sa.Column('current_step_id', sa.UUID(), nullable=True),
        sa.Column('status', postgresql.ENUM('active', 'paused', 'completed', name='funnelstatus', create_type=False), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['current_step_id'], ['funnel_steps.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['funnel_id'], ['funnels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_funnel_state_current_step_id'), 'user_funnel_state', ['current_step_id'], unique=False)
    op.create_index(op.f('ix_user_funnel_state_funnel_id'), 'user_funnel_state', ['funnel_id'], unique=False)
    op.create_index(op.f('ix_user_funnel_state_user_id'), 'user_funnel_state', ['user_id'], unique=False)
    
    op.create_table('user_tags',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('tag', sa.String(length=128), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.telegram_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'tag'),
        sa.UniqueConstraint('user_id', 'tag', name='uq_user_tags_user_id_tag')
    )
    op.create_index(op.f('ix_user_tags_tag'), 'user_tags', ['tag'], unique=False)
    op.create_index(op.f('ix_user_tags_user_id'), 'user_tags', ['user_id'], unique=False)

def downgrade() -> None:
    op.drop_table('user_tags')
    op.drop_table('user_funnel_state')
    op.drop_table('scheduled_tasks')
    op.drop_table('purchases')
    op.drop_table('users')
    op.drop_table('funnel_steps')
    op.drop_table('tracks')
    op.drop_table('products')
    op.drop_table('funnels')
    op.drop_table('bot_settings')

    sa.Enum('allow', 'deny', name='funnelcrossentrybehavior').drop(op.get_bind())
    sa.Enum('active', 'paused', 'completed', name='funnelstatus').drop(op.get_bind())
    sa.Enum('pending', 'paid', 'failed', 'refunded', name='paymentstatus').drop(op.get_bind())
    sa.Enum('pending', 'processing', 'done', 'canceled', 'failed', name='scheduledtaskstatus').drop(op.get_bind())
