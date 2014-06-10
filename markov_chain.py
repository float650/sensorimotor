import numpy as np
import cPickle as cp
import theano
import theano.tensor as T

from theano.sandbox.rng_mrg import MRG_RandomStreams as RandomStreams
import time
from matplotlib import pyplot as pp

from models import LinearGaussian as Lmodel
from inference_engines import ParticleFilter
from learning_algs import SGD_Momentum_Learner as SGDLearner

statedims=2
datadims=10
nparticles=400

n_joint_samples=20

nt=80000

#======Making data=======================
antisym=np.tril(np.ones((statedims, statedims)),k=-1); antisym=antisym-antisym.T
trueM=np.eye(statedims,k=1)*8e-2
trueM=trueM+trueM.T; trueM=trueM*antisym+np.eye(statedims)
trueG=np.random.randn(statedims,datadims)*4.0
true_log_stddev=np.random.randn(statedims)-10.0

s0=np.zeros(statedims); s0[0]=1.0; s0=s0.astype(np.float32)
true_s=[s0]
for i in range(nt):
	next_s=np.dot(true_s[i],trueM)
	next_s=next_s/np.sqrt(np.sum(next_s**2))
	true_s.append(next_s+np.random.randn(statedims)*np.exp(true_log_stddev))
true_s=np.asarray(true_s,dtype='float32')
observations=np.dot(true_s,trueG)+np.random.randn(true_s.shape[0],datadims)*np.exp(-4.0)

#pp.plot(true_s)
#pp.figure(2)
#pp.plot(observations)
#pp.show()

shared_obs=theano.shared(observations.astype(np.float32))
shared_t=theano.shared(0)
current_observation=shared_obs[shared_t]
increment_t=theano.function([],updates={shared_t: shared_t+1})
#========================================

genproc=Lmodel(statedims, datadims)
tranproc=Lmodel(statedims, statedims)

PF=ParticleFilter(tranproc, genproc, nparticles, n_history=1, observation_input=current_observation)


tranproc.M.set_value(np.eye(statedims).astype(np.float32))
tranproc.log_stddev.set_value((np.ones(statedims)*-2.0).astype(np.float32))

prop_distrib = tranproc.get_samples(PF.current_state)

PF.set_proposal(prop_distrib)

#PF.set_true_log_observation_probs(genproc.rel_log_prob)
#PF.set_true_log_transition_probs(tranproc.rel_log_prob)

PF.recompile()

#total_params=tranproc.params + genproc.params
total_params=[tranproc.M, genproc.M, tranproc.log_stddev, genproc.log_stddev]

obs=T.fvector()
shared_joint_samples=theano.shared(np.zeros((2, n_joint_samples, statedims)).astype(np.float32))

joint_samples, joint_sample_updates=PF.sample_from_joint(n_joint_samples)
joint_sample_updates[shared_joint_samples]=joint_samples
perform_joint_sampling=theano.function([],updates=joint_sample_updates)

tranloss=T.mean(tranproc.rel_log_prob(shared_joint_samples[0],shared_joint_samples[1],include_params_in_Z=True))
genloss=T.mean(genproc.rel_log_prob(shared_joint_samples[1],current_observation.dimshuffle('x',0),include_params_in_Z=True))
total_loss=-(tranloss+genloss)
#lrates=np.asarray([1.0, 0.0, 0.0, 1.0, 0.0, 0.0])*2e-4
lrates=np.asarray([1.0, 1.0])*1e-0

#learner=SGDLearner(total_params, total_loss, init_lrates=lrates)
learner=SGDLearner(total_params, total_loss, init_lrates=[2e-5])




print 'Done compiling, beginning training'
esshist=[]
t0=time.time()
statehist=[]
weighthist=[]
learn_every=10
for i in range(nt-1000):
	PF.perform_inference()
	ess=PF.get_ESS()
	esshist.append(ess)
	statehist.append(PF.get_current_particles())
	weighthist.append(PF.get_current_weights())
	
	if (i+1)%learn_every==0:
		perform_joint_sampling()
		loss0=learner.get_current_loss()
		learner.perform_learning_step()
		loss1=learner.get_current_loss()
		print loss1-loss0
	
	if ess<nparticles/2:
		PF.resample()
	
	increment_t()

print tranproc.M.get_value()
print trueM
print tranproc.log_stddev.get_value()
print true_log_stddev
print genproc.log_stddev.get_value()

futuresamps=PF.sample_from_future(100,1000)
futuremeans=np.mean(futuresamps,axis=1)

statehist=np.asarray(statehist,dtype='float32')
weighthist=np.asarray(weighthist,dtype='float32')

meanstate=np.sum(statehist*np.reshape(weighthist,(statehist.shape[0],statehist.shape[1],1)),axis=1)

losshist=np.asarray(learner.loss_history)
pp.plot(losshist[:,1])
pp.figure(2)
pp.plot(futuremeans)
pp.plot(observations[-1000:])
pp.figure(3)
pp.plot(meanstate)
pp.show()
