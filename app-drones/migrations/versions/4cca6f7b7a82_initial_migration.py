"""Initial migration.

Revision ID: 4cca6f7b7a82
Revises: 
Create Date: 2024-04-08 23:03:18.148904

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '4cca6f7b7a82'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('videos')
    op.drop_table('usuarios')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    None
    # ### end Alembic commands ###