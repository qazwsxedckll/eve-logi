from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField, FloatField
from wtforms.fields.core import IntegerField
from wtforms.validators import DataRequired, InputRequired, NumberRange


class TradeGoodsForm(FlaskForm):
    structure = SelectField('Market', coerce=int, validators=[DataRequired()])
    multiple = SelectField('multiple of daily volume', coerce=int, validators=[DataRequired()], default=3)
    volume_filter = FloatField('ignore daily volume less than', validators=[InputRequired()], default=0.0)
    quantity_filter = IntegerField('Quantity', validators=[InputRequired()], default=200)
    submit = SubmitField('Submit')