
from .base_world import World as BaseWorld
import numpy as np

class World(BaseWorld):
    """grid_1D_ms.World
    One-dimensional grid task, multi-step
    In this task, the agent steps forward and backward along a line. The fourth position is rewarded 
    and the ninth position is punished. This is intended to be as similar as possible to the 
    one-dimensional grid task, but require multi-step planning for optimal behavior.
    See Chapter 4 of the Users Guide for details.
    Optimal performance is a reward of about 85 per time step.
    """

    def __init__(self, lifespan=None):
        super(World, self).__init__()
        
        if lifespan is None:
            self.LIFESPAN = 10 ** 4
        else:
            self.LIFESPAN = lifespan
        self.REPORTING_PERIOD = 10 ** 4
        self.REWARD_MAGNITUDE = 100.
        self.ENERGY_COST = 0.01 * self.REWARD_MAGNITUDE
        self.JUMP_FRACTION = 0.1
        self.display_state = False
        self.name = 'multi-step one dimensional grid world'
        self.announce()
        
        self.num_sensors = 9
        self.num_actions = 3
        self.MAX_NUM_FEATURES = self.num_sensors + self.num_actions

        self.world_state = 0            
        self.simple_state = 0
        
            
    def step(self, action): 
        if action is None:
            action = np.zeros(self.num_actions)
        action = np.round(action)
        action = action.ravel()
        self.timestep += 1 

        energy = action[0] + action[1]
        self.world_state += action[0] - action[1]
        
        """ Occasionally add a perturbation to the action to knock it into a different state """
        if np.random.random_sample() < self.JUMP_FRACTION:
            self.world_state = self.num_sensors * np.random.random_sample()
                    
        """ Ensure that the world state falls between 0 and 9 """
        self.world_state -= self.num_sensors * np.floor_divide(self.world_state, self.num_sensors)
        self.simple_state = int(np.floor(self.world_state))
        
        """ Assign sensors as zeros or ones. 
        Represent the presence or absence of the current position in the bin.
        """
        sensors = np.zeros(self.num_sensors)
        sensors[self.simple_state] = 1
        
        """ Assign reward based on the current state """
        reward = sensors[8] * (-self.REWARD_MAGNITUDE)
        reward += sensors[3] * (self.REWARD_MAGNITUDE)
        
        """ Punish actions just a little """
        reward -= energy * self.ENERGY_COST
        reward = np.max(reward, -1)
        
        self.display()
        return sensors, reward

                    
    def set_agent_parameters(self, agent):
        """ Prevent the agent from forming any groups """
        #agent.perceiver.NEW_FEATURE_THRESHOLD = 1.0
        agent.reward_min = -100.
        agent.reward_max = 100.
        #agent.level1.cogs[0].map.NEW_FEATURE_THRESHOLD = 0.1
        #agent.level1.cogs[0].map.PLASTICITY_UPDATE_RATE = 0.1 * agent.level1.cogs[0].map.NEW_FEATURE_THRESHOLD


    def display(self):
        """ Provide an intuitive display of the current state of the World to the user """
        if (self.display_state):
            state_image = ['.'] * self.num_sensors
            state_image[self.simple_state] = 'O'
            self.node.publish(''.join(state_image))
            
        if (self.timestep % self.REPORTING_PERIOD) == 0:
            self.node.publish("world age is %s timesteps " % self.timestep)

            print("world age is %s timesteps " % self.timestep)