import test_common
from spartan import expr
from spartan.expr.optimize import optimize
from spartan.examples import finance

maturity = 10.0
rate = 0.005
volatility = 0.001

class TestFinance(test_common.ClusterTest):
  TILE_SIZE = 5
  def setUp(self):
    if not hasattr(self, 'current'):
      self.current = expr.abs(10 + expr.randn(10))
      self.strike = expr.abs(20 + expr.randn(10))

  def test_call(self):
    put, call = finance.black_scholes(self.current, self.strike, maturity, rate, volatility)
    print optimize(call)
    print call.glom()

  def test_put(self):
    put, call = finance.black_scholes(self.current, self.strike, maturity, rate, volatility)
    print optimize(put)
    print put.glom()

  def test_find_change(self):
    arr = expr.randn(100)
    movers = finance.find_change(arr)
    print optimize(movers)
    print movers.glom().compressed()