
from flask_wtf import FlaskForm
from wtforms import IntegerField, SubmitField, StringField, FloatField, SelectField
from wtforms.validators import DataRequired, InputRequired, NumberRange, Length, Regexp


class StructureForm(FlaskForm):
    structure_id = StringField('Structure ID', validators=[InputRequired()])
    name = StringField('Structure Name', validators=[InputRequired(), Length(0, 32, message='Struct Name too long!'), Regexp(
        '^[a-zA-Z0-9_-]*$', message='The name should contain only a-z, A-Z, 0-9, - and _.')])
    jita_to_fee = IntegerField('Jita To Fee', validators=[InputRequired(), NumberRange(0)], default=0)
    jita_to_collateral = FloatField(
        'Jita To Collateral(%)', validators=[InputRequired(), NumberRange(0)], default=0)
    to_jita_fee = IntegerField('To Jita Fee', validators=[InputRequired(), NumberRange()], default=0)
    to_jita_collateral = FloatField(
        'To Jita Collateral(%)', validators=[InputRequired(), NumberRange(0)], default=0)
    sales_tax = FloatField('Sales Tax(%)', validators=[InputRequired(), NumberRange(0)], default=0)
    brokers_fee = FloatField('Brokers Fee(%)', validators=[InputRequired(), NumberRange(0)], default=0)
    character_id = SelectField(
        'Character To Bind', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Submit')
