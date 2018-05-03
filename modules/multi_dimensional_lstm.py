from modules.multi_dimensional_rnn import MultiDimensionalRNN
from modules.multi_dimensional_rnn import MultiDimensionalRNNBase
import util.tensor_flipping
import torch
import torch.nn.functional as F
import torch.nn
import torch.nn as nn
from modules.state_update_block import StateUpdateBlock
from modules.multi_dimensional_lstm_parameters import MultiDimensionalLSTMParametersOneDirection
from modules.multi_dimensional_lstm_parameters import MultiDimensionalLSTMParametersOneDirectionFast
from modules.multi_dimensional_lstm_parameters import MultiDimensionalLSTMParametersCreator
from modules.multi_dimensional_lstm_parameters import MultiDimensionalLSTMParametersCreatorSlow
from modules.multi_dimensional_lstm_parameters import MultiDimensionalLSTMParametersCreatorFast


class MultiDimensionalLSTM(MultiDimensionalRNNBase):

    def __init__(self, hidden_states_size, batch_size, compute_multi_directional: bool,
                 use_dropout: bool, training: bool,
                 multi_dimensional_lstm_parameter_creator:MultiDimensionalLSTMParametersCreator,
                 nonlinearity="tanh"):
        super(MultiDimensionalLSTM, self).__init__(hidden_states_size, batch_size,
                                                  compute_multi_directional,
                                                  nonlinearity)

        self.use_dropout = use_dropout
        self.training = training

        self.mdlstm_direction_one_parameters = \
            multi_dimensional_lstm_parameter_creator.create_multi_dimensional_lstm_parameters_one_direction(
                self.hidden_states_size, self.input_channels, use_dropout)

        # Set initial bias for the forget gates to one, since it is known to give better results
        self.mdlstm_direction_one_parameters.set_bias_forget_gates_to_one()

        self.fc3 = nn.Linear(self.number_of_output_dimensions(), 10)

        # print("self.fc3 : " + str(self.fc3))
        # print("self.fc3.weight: " + str(self.fc3.weight))
        # print("self.fc3.bias: " + str(self.fc3.bias))

        # For multi-directional rnn
        if self.compute_multi_directional:
            self.mdlstm_direction_two_parameters = \
                multi_dimensional_lstm_parameter_creator.create_multi_dimensional_lstm_parameters_one_direction(
                    self.hidden_states_size, self.input_channels, use_dropout)
            # Set initial bias for the forget gates to one, since it is known to give better results
            self.mdlstm_direction_two_parameters.set_bias_forget_gates_to_one()

            self.mdlstm_direction_three_parameters = \
                multi_dimensional_lstm_parameter_creator.create_multi_dimensional_lstm_parameters_one_direction(
                    self.hidden_states_size, self.input_channels, use_dropout)
            # Set initial bias for the forget gates to one, since it is known to give better results
            self.mdlstm_direction_three_parameters.set_bias_forget_gates_to_one()

            self.mdlstm_direction_four_parameters = \
                multi_dimensional_lstm_parameter_creator.create_multi_dimensional_lstm_parameters_one_direction(
                    self.hidden_states_size, self.input_channels, use_dropout)
            # Set initial bias for the forget gates to one, since it is known to give better results
            self.mdlstm_direction_four_parameters.set_bias_forget_gates_to_one()

        self.state_convolutions = nn.ModuleList([])
        self.register_parameters_to_assure_same_gpu_is_used()

    def register_parameters_to_assure_same_gpu_is_used(self):
        self.state_convolutions.extend(self.mdlstm_direction_one_parameters.get_all_parameters_as_list())

        if self.compute_multi_directional:
            self.state_convolutions.extend(self.mdlstm_direction_two_parameters.get_all_parameters_as_list())
            self.state_convolutions.extend(self.mdlstm_direction_three_parameters.get_all_parameters_as_list())
            self.state_convolutions.extend(self.mdlstm_direction_four_parameters.get_all_parameters_as_list())



    @staticmethod
    def create_multi_dimensional_lstm(hidden_states_size:int ,batch_size:int , compute_multi_directional: bool,
                                      use_dropout: bool,
                                     nonlinearity="tanh"):
        return MultiDimensionalLSTM(hidden_states_size, batch_size, compute_multi_directional, use_dropout,
                                    True,
                                    MultiDimensionalLSTMParametersCreatorSlow(),
                                    nonlinearity)

    @staticmethod
    def create_multi_dimensional_lstm_fast(hidden_states_size: int, batch_size: int, compute_multi_directional: bool,
                                      use_dropout: bool,
                                      nonlinearity="tanh"):
        return MultiDimensionalLSTM(hidden_states_size, batch_size, compute_multi_directional, use_dropout,
                                    True,
                                    MultiDimensionalLSTMParametersCreatorFast(),
                                    nonlinearity)

    def set_training(self, training):
        self.mdlstm_direction_one_parameters.set_training(training)

        if self.compute_multi_directional:
            self.mdlstm_direction_two_parameters.set_training(training)
            self.mdlstm_direction_three_parameters.set_training(training)
            self.mdlstm_direction_four_parameters.set_training(training)

        self.training = training

    def compute_multi_dimensional_lstm_one_direction(self, mdlstm_parameters, x):
        if MultiDimensionalRNNBase.use_cuda():
            # https://discuss.pytorch.org/t/which-device-is-model-tensor-stored-on/4908/7
            device = x.get_device()

        # Step 1: Create a skewed version of the input image
        # skewed_image = ImageInputTransformer.create_row_diagonal_offset_tensor(x)
        skewed_images_variable = MultiDimensionalRNNBase.create_skewed_images_variable_four_dim(x)
        # print("list(x.size()): " + str(list(x.size())))
        image_height = x.size(2)
        # print("image height: " + str(image_height))
        previous_hidden_state_column = torch.zeros(self.input_channels,
                                                   self.hidden_states_size,
                                                   image_height,
                                                   requires_grad=True)

        # and previous_hidden_state: why the latter has dimension equal to
        # batch size but for the former it doesn't seem to matter
        previous_memory_state_column = torch.zeros(self.input_channels,
                                                   self.hidden_states_size,
                                                   image_height,
                                                   requires_grad=True)

        # After initialization, the value of grad_fn is still None, later it gets set
        # print("initialization: previous_memory_state_column.grad_fn: " + str(previous_memory_state_column.grad_fn))
        # print("initialization: previous_hidden_state_column.grad_fn: " + str(previous_hidden_state_column.grad_fn))

        if MultiDimensionalRNNBase.use_cuda():
            previous_hidden_state_column = previous_hidden_state_column.to(device)
            previous_memory_state_column = previous_memory_state_column.to(device)

        skewed_image_columns = skewed_images_variable.size(3)

        # print("mdlstm_parameters.input_input_convolution: " + str(mdlstm_parameters.input_input_convolution))
        # print("skewed_images_variable: " + str(skewed_images_variable))
        # print("mdlstm_parameters.input_input_convolution.bias: "
        # + str(mdlstm_parameters.input_input_convolution.bias))
        input_input_matrix = mdlstm_parameters.input_input_convolution(skewed_images_variable)
        # print("input_matrix: " + str(input_matrix))

        input_gate_input_matrix = mdlstm_parameters.input_gate_input_convolution(skewed_images_variable)
        forget_gate_one_input_matrix = mdlstm_parameters.forget_gate_one_input_convolution(skewed_images_variable)
        forget_gate_two_input_matrix = mdlstm_parameters.forget_gate_two_input_convolution(skewed_images_variable)
        output_gate_input_matrix = mdlstm_parameters.output_gate_input_convolution(skewed_images_variable)

        activations = list([])

        # print("skewed image columns: " + str(skewed_image_columns))

        for column_number in range(0, skewed_image_columns):

            #Preparation of the computations of the next state. This involves either just
            # storing the previous hidden state and previous memory state columns in the
            # mdlstm_parameters class or already part of the computation, depending on the
            # implementaiton of mdlstm_parameters

            # print("previous hidden state column: " + str(previous_hidden_state_column))
            # print("previous memory state column: " + str(previous_memory_state_column))
            mdlstm_parameters.prepare_computation_next_column_functions(previous_hidden_state_column,
                                                                        previous_memory_state_column)


            # Compute convolution on previous state column vector padded with zeros
            # Compute convolution on previous state column vector padded with zeros
            input_hidden_state_column = mdlstm_parameters.get_input_hidden_state_column()

            # print("state_column.size(): " + str(state_column.size()))
            input_state_plus_input = MultiDimensionalRNNBase.compute_states_plus_input(input_input_matrix,
                                                                                       column_number,
                                                                                       input_hidden_state_column)

            # Compute the sum of weighted inputs of the input gate
            input_gate_weighted_states_plus_input = MultiDimensionalLSTM.\
                compute_weighted_input_input_gate(column_number, input_gate_input_matrix,
                                                  mdlstm_parameters)


            # Compute the input activation
            input_activation_column = F.tanh(input_state_plus_input)
            #input_activation_column = F.relu(input_state_plus_input) # Relu can be used as an alternative to tanh
            # Compute the input gate activation
            input_gate_activation_column = F.sigmoid(input_gate_weighted_states_plus_input)

            input_and_input_gate_combined = torch.mul(input_activation_column, input_gate_activation_column)
            # print("input and input gate combined: " + str(input_and_input_gate_combined))

            memory_states_column_forget_gate_one = previous_memory_state_column

            forget_gate_one_weighted_states_plus_input = self.compute_weighted_input_forget_gate(
                mdlstm_parameters.get_forget_gate_one_hidden_state_column(),
                mdlstm_parameters.get_forget_gate_one_memory_state_column(),
                column_number, forget_gate_one_input_matrix)

            # print(">>> forget_gate_one_weighted_states_plus_input: " + str(forget_gate_one_weighted_states_plus_input))

            # Compute the forget gate one activation
            forget_gate_one_activation_column = F.sigmoid(forget_gate_one_weighted_states_plus_input)
            # print("forget gate one activation column: " + str(forget_gate_one_activation_column))

            # Compute the activation for forget gate one
            forget_gate_one_activation_multiplied_with_previous_memory_state = \
                torch.mul(forget_gate_one_activation_column,
                          memory_states_column_forget_gate_one)

            memory_states_column_forget_gate_two = StateUpdateBlock.\
                get_shifted_column_fast(previous_memory_state_column)

            forget_gate_two_weighted_states_plus_input = self.compute_weighted_input_forget_gate(
                mdlstm_parameters.get_forget_gate_two_hidden_state_column(),
                mdlstm_parameters.get_forget_gate_two_memory_state_column(),
                column_number, forget_gate_two_input_matrix)

            # Compute the forget gate two activation
            forget_gate_two_activation_column = F.sigmoid(forget_gate_two_weighted_states_plus_input)


            # forget_gate_weighted_states_combined =  forget_gate_one_weighted_stated_plus_input + forget_gate_two_weighted_stated_plus_input
            # forget_gates_combined_activation_column = F.sigmoid(forget_gate_weighted_states_combined)
            # forget_gates_combined_activation_multiplied_with_previous_memory_state = torch.mul(
            #    forget_gates_combined_activation_column, previous_memory_state_column)

            # Compute the activation for forget gate two
            forget_gate_two_activation_multiplied_with_previous_memory_state = torch.mul(
                forget_gate_two_activation_column, memory_states_column_forget_gate_two)

            # print("input_and_input_gate_combined: " + str(input_and_input_gate_combined))

            # print("forget_gate_one_activation_column: " + str(forget_gate_two_activation_column))
            # print("memory_states_column_forget_gate_one: " + str(memory_states_column_forget_gate_one))
            # print("forget_gate_two_activation_column: " + str(forget_gate_two_activation_column))
            #print("memory_states_column_forget_gate_two: " + str(memory_states_column_forget_gate_two))
            #print("forget_gate_one_activation_multiplied_with_previous_memory_state: "+
            #      str(forget_gate_one_activation_multiplied_with_previous_memory_state))
            #print("forget_gate_two_activation_multiplied_with_previous_memory_state: " +
            #      str(forget_gate_two_activation_multiplied_with_previous_memory_state))

            new_memory_state = input_and_input_gate_combined + \
                forget_gate_two_activation_multiplied_with_previous_memory_state + \
                forget_gate_one_activation_multiplied_with_previous_memory_state # + \
                # forget_gates_combined_activation_multiplied_with_previous_memory_state \

            #new_memory_state = input_and_input_gate_combined + \
            #    forget_gate_two_activation_multiplied_with_previous_memory_state


            # print("new memory state: " + str(new_memory_state))

            # This additional tanh activation function taken from the NVIDIA diagram
            # was not in the deep learning book diagram, and does not seem to help
            # really ?
            new_memory_state_activation_column = F.tanh(new_memory_state)

            # Compute the sum of weighted inputs of the ouput gate
            output_gate_weighted_states_plus_input = self. \
                compute_weighted_input_output_gate(mdlstm_parameters, new_memory_state,
                                                   column_number, output_gate_input_matrix)



            output_gate_activation_column = F.sigmoid(output_gate_weighted_states_plus_input)

            # print("input_column: " + str(input_column))
            #print("state_plus_input: " + str(state_plus_input))
            #activation_column = torch.mul(new_memory_state_activation_column, output_gate_activation_column)
            #activation_column = torch.mul(new_memory_state, output_gate_activation_column)
            #activation_column = self.get_activation_function()(input_state_plus_input)
            activation_column = new_memory_state_activation_column
            # print("output gate activation column: " + str(output_gate_activation_column))
            #print("activation column: " + str(activation_column))

            previous_hidden_state_column = activation_column
            previous_memory_state_column = new_memory_state
            activations.append(activation_column)

            # In the loop the value of grad_fn becomes set, as a backwards path for
            # back-propagation is collected
            # print("in loop: previous_memory_state_column.grad_fn: " + str(previous_memory_state_column.grad_fn))
            # print("in loop: previous_hidden_state_column.grad_fn: " + str(previous_hidden_state_column.grad_fn))

        original_image_columns = x.size(2)
        skewed_image_rows = skewed_images_variable.size(2)

        activations_unskewed = MultiDimensionalRNNBase.extract_unskewed_activations(activations,
                                                                                    original_image_columns,
                                                                                    skewed_image_columns,
                                                                                    skewed_image_rows)

        # print("activations_unskewed: " + str(activations_unskewed))
        return activations_unskewed

        # This function is slow because all four function calls for 4 directions are
        # executed sequentially. It isn't entirely clear how to optimize this.
        # See the discussion at:
        # https://discuss.pytorch.org/t/is-there-a-way-to-parallelize-independent-sequential-steps/3360

    def forward_multi_directional_multi_dimensional_lstm(self, x):
        # print("list(x.size()): " + str(list(x.size())))

        # Original order
        activations_unskewed_direction_one = self.\
            compute_multi_dimensional_lstm_one_direction(self.mdlstm_direction_one_parameters, x)
        activations_one_dimensional_one = activations_unskewed_direction_one.view(-1, 1024 * self.hidden_states_size)

        # Flipping 2nd dimension
        activations_unskewed_direction_two = self.compute_multi_dimensional_lstm_one_direction(
            self.mdlstm_direction_two_parameters, util.tensor_flipping.flip(x, 2))
        activations_one_dimensional_two = activations_unskewed_direction_two.view(-1, 1024 * self.hidden_states_size)

        # print("activations_one_dimensional_two: " + str(activations_one_dimensional_two))

        # Flipping 3th dimension
        activations_unskewed_direction_three = self.compute_multi_dimensional_lstm_one_direction(
            self.mdlstm_direction_three_parameters, util.tensor_flipping.flip(x, 3))
        activations_one_dimensional_three = activations_unskewed_direction_three.view(-1, 1024 * self.hidden_states_size)

        # Flipping 2nd and 3th dimension combined
        activations_unskewed_direction_four = self.compute_multi_dimensional_lstm_one_direction(
            self.mdlstm_direction_four_parameters, util.tensor_flipping.flip(util.tensor_flipping.flip(x, 2), 3))
        activations_one_dimensional_four = activations_unskewed_direction_four.view(-1, 1024 * self.hidden_states_size)

        activations_combined = torch.cat((activations_one_dimensional_one, activations_one_dimensional_two,
                                          activations_one_dimensional_three, activations_one_dimensional_four), 1)

        # print("activations_combined: " + str(activations_combined))

        # print("activations_one_dimensional: " + str(activations_one_dimensional))
        # It is nescessary to output a tensor of size 10, for 10 different output classes
        result = self.fc3(activations_combined)
        return result

    @staticmethod
    def compute_weighted_input_input_gate(column_number, input_gate_input_matrix, mdlstm_parameters):
        input_gate_input_column = input_gate_input_matrix[:, :, :, column_number]
        input_gate_hidden_state_column = mdlstm_parameters.get_input_gate_hidden_state_column()
        input_gate_memory_state_column = mdlstm_parameters.get_input_gate_memory_state_column()
        input_gate_weighted_states_plus_weighted_input = input_gate_input_column + \
            input_gate_hidden_state_column + input_gate_memory_state_column
        return input_gate_weighted_states_plus_weighted_input

    def compute_weighted_input_output_gate(self, mdlstm_parameters,
                                           previous_memory_state_column,
                                           column_number, output_gate_input_matrix):

        if self.use_dropout:
            output_gate_memory_state_column = \
                F.dropout(StateUpdateBlock.compute_weighted_state_input_state_one(
                    mdlstm_parameters.output_gate_memory_state_convolution,
                    previous_memory_state_column), p=0.2, training=self.training)
        else:
            output_gate_memory_state_column = StateUpdateBlock. \
                compute_weighted_state_input_state_one(mdlstm_parameters.output_gate_memory_state_convolution,
                                                       previous_memory_state_column)

        return self.compute_weighted_input_forget_gate(
                mdlstm_parameters.get_output_gate_hidden_state_column(),
                output_gate_memory_state_column,
                column_number, output_gate_input_matrix)

    @staticmethod
    def compute_weighted_input_forget_gate(forget_gate_hidden_state_column,
                                           forget_gate_memory_state_column,
                                           column_number, forget_gate_input_matrix):

        forget_gate_input_column = forget_gate_input_matrix[:, :, :, column_number]
        forget_gate_weighted_states_plus_weighted_input = forget_gate_input_column + forget_gate_hidden_state_column + \
            forget_gate_memory_state_column

        # print("forget_gate_memory_state_column: " + str(forget_gate_memory_state_column))
        # print("forget_gate_hidden_state_column: " + str(forget_gate_hidden_state_column))
        # print("forget_gate_input_column: " + str(forget_gate_input_column))

        # print("forget_gate_weighted_states_plus_weighted_input: " + str(forget_gate_weighted_states_plus_weighted_input))

        return forget_gate_weighted_states_plus_weighted_input

    def forward_one_directional_multi_dimensional_lstm(self, x):
        activations_unskewed = self.compute_multi_dimensional_lstm_one_direction(self.mdlstm_direction_one_parameters, x)
        activations_one_dimensional = activations_unskewed.view(-1, self.number_of_output_dimensions())
        # print("activations_one_dimensional: " + str(activations_one_dimensional))
        # It is necessary to output a tensor of size 10, for 10 different output classes
        # print("self.fc3.weight: " + str(self.fc3.weight))
        # print("self.fc3.bias: " + str(self.fc3.bias))
        result = self.fc3(activations_one_dimensional)
        return result

    def _final_activation_function(self, final_activation_function_input):
        return self.fc3(final_activation_function_input)

    # Needs to be implemented in the subclasses
    def _compute_multi_dimensional_function_one_direction(self, function_input):
        return self.compute_multi_dimensional_lstm_one_direction(self.mdlstm_direction_one_parameters, function_input)

    # Input tensor x is a batch of image tensors
    def forward(self, x):
        if self.compute_multi_directional:
            # With distinct parameters for every direction
            return self.forward_multi_directional_multi_dimensional_lstm(x)
            # With same paramters for every direction
            #return self.forward_multi_directional_multi_dimensional_function_fast(x)
        else:
            return self.forward_one_directional_multi_dimensional_lstm(x)
