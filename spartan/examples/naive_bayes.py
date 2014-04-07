import numpy as np
from spartan import expr, util
from spartan.array import extent, distarray

def _naive_bayes_mapper(array, ex, weights_per_label, alpha):
  '''
  train local naive bayes weights.
  
  Args:
    array(DistArray): weights for each label and feature.
    ex(Extent): Region being processed.
    weights_per_label(DistArray): weights for each label.
    alpha: naive bayes parameter.
  '''
  weights_per_label_and_feature = array.fetch(ex)
  weights_per_label = weights_per_label.fetch(extent.create((ex.ul[0], 0), (ex.lr[0], 1), weights_per_label.shape))

  weights_per_label_and_feature = np.log((weights_per_label_and_feature + alpha)/(weights_per_label + alpha * weights_per_label_and_feature.shape[1]))

  yield ex, weights_per_label_and_feature
  
def _sum_instance_by_label_mapper(array, ex, labels, label_size):
  '''
  sum up all the feature vectors with the same labels for each label.
  
  Args:
    array(DistArray): tf-idf normalized training data.
    ex(Extent): Region being processed.
    labels(DistArray): labels of the training data.
    label_size: the number of different labels.
  '''
  X = array.fetch(ex)
  Y = labels.fetch(extent.create((ex.ul[0], 0), (ex.lr[0], 1), labels.shape))
  
  sum_instance_by_label = np.zeros((label_size, X.shape[1]))
  for i in xrange(Y.shape[0]):
    sum_instance_by_label[Y[i,0]] += X[i]
    
  yield extent.create((0,0),(label_size, X.shape[1]),(label_size, X.shape[1])), sum_instance_by_label
  
def fit(data, labels, label_size, alpha=1.0):
  '''
  Train standard naive bayes model.
 
  Args:
    data(Expr): documents to be trained.
    labels(Expr): the correct labels of the training data.
    label_size(int): the number of different labels.
    alpha(float): alpha parameter of naive bayes model.
  '''
  labels = expr.force(labels)
  
  # calc document freq
  df = expr.reshape(expr.reduce(data,
                                axis=0,
                                dtype_fn=lambda input: input.dtype,
                                local_reduce_fn=lambda ex, data, axis: (data > 0).sum(axis),
                                accumulate_fn=np.add,
                                tile_hint=(data.shape[1],)),
                    (1, data.shape[1])) 
  
  idf = expr.log(data.shape[0] * 1.0 / (df + 1)) + 1
   
  # Normalized Frequency for a feature in a document is calculated by dividing the feature frequency 
  # by the root mean square of features frequencies in that document
  square_sum = expr.reshape(expr.reduce(data,
                                        axis=1,
                                        dtype_fn=lambda input: input.dtype,
                                        local_reduce_fn=lambda ex, data, axis: np.square(data).sum(axis),
                                        accumulate_fn=np.add,
                                        tile_hint=(data.shape[0],)), 
                            (data.shape[0], 1))
  
  rms = expr.sqrt(square_sum * 1.0 / data.shape[1])
  
  # calculate weight normalized Tf-Idf
  data = data / rms * idf
  
  #add up all the feature vectors with the same labels
  sum_instance_by_label = distarray.create((label_size, data.shape[1]), np.float64, reducer=np.add, tile_hint=(label_size/len(labels.tiles), data.shape[1]))
  expr.shuffle(data, _sum_instance_by_label_mapper, target=sum_instance_by_label, kw={'labels': labels, 'label_size': label_size}).force()
  
  #sum up all the weights for each label from the previous step
  weights_per_label = expr.reshape(expr.sum(sum_instance_by_label, axis=1, tile_hint=(label_size,)), (label_size, 1)).force()
  
  #generate naive bayes per_label_and_feature weights
  weights_per_label_and_feature = expr.shuffle(sum_instance_by_label, _naive_bayes_mapper, kw={'weights_per_label': weights_per_label, 'alpha':alpha}).force()
  
  return {'scores_per_label_and_feature': weights_per_label_and_feature, 
          'scores_per_label': weights_per_label, 
          }
  
def predict(model, new_data):
  '''
  Predict the label of the given instance.
  
  Args:
    model(dict): trained naive bayes model.
    new_data(Expr or DistArray): data to be predicted
  '''
  scores_per_label_and_feature = model['scores_per_label_and_feature']

  scoring_vector = expr.dot(scores_per_label_and_feature, expr.transpose(new_data))
  #util.log_warn('scoring_vector:%s', scoring_vector.glom().T)  
  
  return np.argmax(scoring_vector.glom())
  