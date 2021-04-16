
from flask_wtf import FlaskForm
from wtforms import IntegerField, SubmitField, StringField, FloatField, SelectField
from wtforms.validators import DataRequired

class StructureForm(FlaskForm):
    structure_id = StringField('Structure ID', validators=[DataRequired()])
    name = StringField('Structure Name', validators=[DataRequired()])
    jita_to_fee = IntegerField('Jita To Fee')
    jita_to_collateral = FloatField('Jita To Collateral')
    to_jita_fee = IntegerField('To Jita Fee')
    to_jita_collateral = FloatField('To Jita Collateral')
    sales_tax = FloatField('Sales Tax')
    brokers_fee = FloatField('Brokers Fee')
    character_id = SelectField('Character To Bind', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Submit')