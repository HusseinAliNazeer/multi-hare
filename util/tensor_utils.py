import torch
import util.image_visualization

__author__ = "Gideon Maillette de Buy Wenniger"
__copyright__ = "Copyright 2019, Gideon Maillette de Buy Wenniger"
__credits__ = ["Gideon Maillette de Buy Wenniger"]
__license__ = "Apache License 2.0"

class TensorUtils:

    @staticmethod
    def tensors_are_equal(tensor_one, tensor_two):
        # https://stackoverflow.com/questions/32996281/how-to-check-if-two-torch-tensors-or-matrices-are-equal
        # https://discuss.pytorch.org/t/tensor-math-logical-operations-any-and-all-functions/6624
        return torch.eq(tensor_one, tensor_two).all()

    # Debugging method that checks that two lists of (3-dimensional)
    # tensors are equal, visualizing the first pair of tensors it
    # encounters that is not equal, if there is one
    @staticmethod
    def tensors_lists_are_equal(tensor_list_one, tensor_list_two):
        if len(tensor_list_one) != len(tensor_list_two):
            return False

        index = 0
        for tensor_one, tensor_two in zip(tensor_list_one, tensor_list_two):
            if not TensorUtils.tensors_are_equal(tensor_one, tensor_two):
                print("tensor_lists_are_equal --- \n"
                      "tensor_list_one[" + str(index) + "]: \n"  +
                      str(tensor_one) + "\n" + "and " +
                      "tensor_list_two[" + str(index) + "]" +
                      str(tensor_two) + " are not equal.")

                print("showing tensor one:")
                element_without_channel_dimension = tensor_one.squeeze(0)
                util.image_visualization.imshow_tensor_2d(element_without_channel_dimension)

                print("showing tensor two:")
                element_without_channel_dimension = tensor_two.squeeze(0)
                util.image_visualization.imshow_tensor_2d(element_without_channel_dimension)

                return False
            index += 1
        return True

    @staticmethod
    # Debugging method that finds equal slices in a 4-dimensional tensor over the batch dimension
    # and visualizes them
    def find_equal_slices_over_batch_dimension(tensor):
        number_or_slices = tensor.size(0)

        for slice_one_index in range(0, number_or_slices):
            tensor_slice_one = tensor[slice_one_index, :, :, :]

            for slice_two_index in range(slice_one_index + 1, number_or_slices):
                tensor_slice_two = tensor[slice_two_index, :, :, :]

                tensors_are_equal = TensorUtils.tensors_are_equal(tensor_slice_one, tensor_slice_two)

                if tensors_are_equal:
                    print("find_equal_slices_over_batch_dimension --- \n"
                          "tensor[" + str(slice_one_index) + ",:,:,:]: \n" +
                          str(tensor_slice_one) + "\n" + "and " +
                          "tensor[" + str(slice_two_index) + "]" +
                          str(tensor_slice_two) + " are equal.")

                    print("showing tensor slice one:")
                    element_without_channel_dimension = tensor_slice_one.squeeze(0)
                    util.image_visualization.imshow_tensor_2d(element_without_channel_dimension)

                    print("showing tensor slice two:")
                    element_without_channel_dimension = tensor_slice_two.squeeze(0)
                    util.image_visualization.imshow_tensor_2d(element_without_channel_dimension)


    @staticmethod
    def number_of_zeros(tensor):
        mask = tensor.eq(0)
        zero_elements = torch.masked_select(tensor, mask).view(-1)
        number_of_zeros = zero_elements.size(0)
        return number_of_zeros

    @staticmethod
    def number_of_non_zeros(tensor):
        mask = tensor.eq(0)
        zero_elements = torch.masked_select(tensor, mask).view(-1)
        number_of_zeros = zero_elements.size(0)
        number_of_elements = tensor.view(-1).size(0)
        return number_of_elements - number_of_zeros


    @staticmethod
    def number_of_ones(tensor):
        mask = tensor.eq(1)
        one_elements = torch.masked_select(tensor, mask).view(-1)
        number_of_ones = one_elements.size(0)
        return number_of_ones

    @staticmethod
    def number_of_non_ones(tensor):
        mask = tensor.eq(1)
        one_elements = torch.masked_select(tensor, mask).view(-1)
        number_of_elements = tensor.view(-1).size(0)
        number_of_ones = one_elements.size(0)
        return number_of_elements - number_of_ones

    @staticmethod
    def sum_list_of_tensors(list_of_tensors):
        result = list_of_tensors[0]

        for index in range(1, len(list_of_tensors)):
            # if TensorUtils.tensors_are_equal(result, list_of_tensors[index]):
            #     print("WARNING - sum_list_of_tensors - tensors are equal")
            # else:
            #     print("INFO - sum_list_of_tensors - tensors are not equal")

            # print("result before addition: " + str(result))
            # print("to add: list_of_tensors[" + str(index) + "]:" + str(list_of_tensors[index]))
            result += list_of_tensors[index]
            # print("result after addition: " + str(result))
        return result



    """
    Applies a binary mask to a tensor. The dimensions of the mask must 
    match the last dimensions of the tensor
    """
    @staticmethod
    def apply_binary_mask(tensor, mask):
        return tensor * mask

    @staticmethod
    def print_max(tensor, variable_name):
        print("max element in " + variable_name + " :" + str(torch.max(tensor)))

    @staticmethod
    def number_of_dimensions(tensor):
        return len(tensor.size())

    @staticmethod
    def chunk_list_of_tensors_along_dimension(list_of_tensors: list, number_of_chunks: int, dim: int,):
        result_lists = list([])
        for i in range(0, number_of_chunks):
            result_lists.append(list([]))
        for tensor in list_of_tensors:
            chunk_tensors = torch.chunk(tensor, number_of_chunks, dim)
            for i in range(0, len(chunk_tensors)):
                result_lists[i].append(chunk_tensors[i])
        return result_lists

    """
    Given a list of tensor lists, all of equal length, this method 
    computes the element-wise summation of tensors with the same index
    in the inner lists
    """
    @staticmethod
    def sum_lists_of_tensor_lists_element_wise(list_of_tensor_lists: list):
        result = list([])
        for element_index in range(0, len(list_of_tensor_lists[0])):

            # Alternative implementation using torch.sum(torch.stack)
            # (Turns out to be not really faster)
            # summation_elements = list([])
            # for list_index in range(0, len(list_of_tensor_lists)):
            #     summation_elements.append(list_of_tensor_lists[list_index][element_index])
            # # https://discuss.pytorch.org/t/how-to-turn-a-list-of-tensor-to-tensor/8868/5
            # # First stack the summation elements along new dimension 0, then sum them
            # # along that dimension
            # activations_summed = torch.sum(torch.stack(summation_elements, 0), 0)

            # Current implementation
            activations_summed = list_of_tensor_lists[0][element_index]
            for list_index in range(1, len(list_of_tensor_lists)):
                activations_summed += list_of_tensor_lists[list_index][element_index]
            result.append(activations_summed)
        return result

    # Return a copy of a list of tensors with every element in pinned memory
    # The idea is that this may help when the list of tensors needs to be moved
    # to GPU, to speed up the data transfer
    @staticmethod
    def get_pinned_memory_copy_of_list(list_of_tensor_lists: list):
        result = list([])
        for tensor in list_of_tensor_lists:
            # See: https://pytorch.org/docs/master/notes/cuda.html
            result.append(tensor.pin_memory())
        return result


def test_number_of_non_zeros():

    tensor = torch.zeros(3, 3)
    print("tensor: " + str(tensor))
    print("number of non-zeros: " + str(TensorUtils.number_of_non_zeros(tensor)))


def main():
    test_number_of_non_zeros()


if __name__ == "__main__":
    main()