from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField
from wtforms.validators import DataRequired


class TradeGoodsForm(FlaskForm):
    structure = SelectField('Market', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Submit')