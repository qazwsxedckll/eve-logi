from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField
from wtforms.validators import DataRequired


class TradeGoodsForm(FlaskForm):
    solar_system = SelectField('SolarSystem', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Submit')