import numpy as np
import keras
from keras.datasets import cifar10
from keras.preprocessing.image import ImageDataGenerator
from keras.models import Model, Input
from keras.layers import Dense, Dropout, Activation, Flatten
from keras.layers import Conv2D, MaxPooling2D
from keras.regularizers import l2

def save_weights(model, filename, stage, block):
    stage = str(stage)
    block = str(block)

    conv1_weights = model.get_layer('conv'+stage+'-'+block+'_i').get_weights()
    conv2_weights = model.get_layer('conv'+stage+'-'+block+'_ii').get_weights()

    np.savez(filename, W_conv1=conv1_weights[0], b_conv1=conv1_weights[1],
                       W_conv2=conv2_weights[0], b_conv2=conv2_weights[1])


    fc1_weights = model.get_layer('fc1').get_weights()
    fc2_weights = model.get_layer('fc2').get_weights()

    np.savez('fc_'+filename, W_fc1=fc1_weights[0], b_fc1=fc1_weights[1],
                       W_fc2=fc2_weights[0], b_fc2=fc2_weights[1])


def load_weights(filename):
    weights = np.load(filename)
    return [[weights["W_conv1"], weights["b_conv1"]], [weights["W_conv2"], weights["b_conv2"]]]

def load_fc_weights(filename):
    weights = np.load(filename)
    return [[weights["W_fc1"], weights["b_fc1"]], [weights["W_fc2"], weights["b_fc2"]]]

def load_conv_weights(filename):
    weights = np.load(filename)
    return [weights["W_conv"], weights["b_conv"]]

def residual_block(input_tensor, num_filters, stage, block, trainable=True, weights=[]):
    stage = str(stage)
    block = str(block)

    trunc_norm = keras.initializers.TruncatedNormal(mean=0.0, stddev=0.001, seed=None)

    # module structure proposed in http://arxiv.org/abs/1603.05027
    if trainable:
        x = keras.layers.BatchNormalization()(input_tensor)
        x = Activation('relu')(x)
        x = Dropout(.3)(x)
        x = Conv2D(num_filters, (3,3), padding='same',
                    kernel_regularizer=l2(1e-6),
                    kernel_initializer=trunc_norm,
                    name='conv'+stage+'-'+block+'_i')(x)
        x = keras.layers.BatchNormalization()(x)
        x = Activation('relu')(x)
        x = Dropout(.3)(x)
        x = Conv2D(num_filters, (3,3), padding='same',
                kernel_regularizer=l2(1e-6),
                kernel_initializer=trunc_norm,
                name='conv'+stage+'-'+block+'_ii',
                )(x)
        x = keras.layers.add([input_tensor, x])
        return x
    else:
        if not weights:
            raise ValueError("weights list cannot be empty")

        x = keras.layers.BatchNormalization()(input_tensor)
        x = Activation('relu')(x)
        x = Conv2D(num_filters, (3,3), padding='same', trainable=False,
                weights=weights[0],
                name='conv'+stage+'-'+block+'_i')(x)
        x = keras.layers.BatchNormalization()(x)
        x = Activation('relu')(x)
        x = Conv2D(num_filters, (3,3), padding='same', trainable=False,
                weights=weights[1],
                name='conv'+stage+'-'+block+'_ii')(x)

        x = keras.layers.add([input_tensor, x])
        return x

def layer11(epochs):
    batch_size = 100
    num_classes = 10
    data_augmentation = True

    # The data, shuffled and split between train and test sets:
    (x_train, y_train), (x_test, y_test) = cifar10.load_data()
    print('x_train shape:', x_train.shape)
    print(x_train.shape[0], 'train samples')
    print(x_test.shape[0], 'test samples')

    # Convert class vectors to binary class matrices.
    y_train = keras.utils.to_categorical(y_train, num_classes)
    y_test = keras.utils.to_categorical(y_test, num_classes)

    main_input = Input(shape=x_train.shape[1:], name='main_input')

    conv1 = Conv2D(64, (3,3), kernel_regularizer=l2(1e-6), name='conv1')(main_input)
    block1 = residual_block(conv1, 64, 1, 1)

    flat = Flatten()(block1)

    fc1 = Dense(512, activation='relu', name='fc1')(flat)
    fc1_drop = Dropout(.5)(fc1)
    main_output = Dense(10, activation='softmax', name='fc2')(fc1_drop)

    model = Model(inputs=[main_input], outputs=[main_output])
    model.compile(optimizer='adam',
                  loss='categorical_crossentropy',
                  metrics=['accuracy'])

    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')
    x_train /= 255
    x_test /= 255

    if not data_augmentation:
        print('Not using data augmentation.')
        model.fit(x_train, y_train,
                  batch_size=batch_size,
                  epochs=epochs,
                  validation_data=(x_test, y_test),
                  shuffle=True)
    else:
        print('Using real-time data augmentation.')
        # This will do preprocessing and realtime data augmentation:
        datagen = ImageDataGenerator(
            featurewise_center=False,  # set input mean to 0 over the dataset
            samplewise_center=False,  # set each sample mean to 0
            featurewise_std_normalization=False,  # divide inputs by std of the dataset
            samplewise_std_normalization=False,  # divide each input by its std
            zca_whitening=False,  # apply ZCA whitening
            rotation_range=0,  # randomly rotate images in the range (degrees, 0 to 180)
            width_shift_range=0.1,  # randomly shift images horizontally (fraction of total width)
            height_shift_range=0.1,  # randomly shift images vertically (fraction of total height)
            horizontal_flip=True,  # randomly flip images
            vertical_flip=False)  # randomly flip images

        # Compute quantities required for feature-wise normalization
        # (std, mean, and principal components if ZCA whitening is applied).
        datagen.fit(x_train)

        # Fit the model on the batches generated by datagen.flow().
        history = model.fit_generator(datagen.flow(x_train, y_train,
                                         batch_size=batch_size),
                            steps_per_epoch=x_train.shape[0] // batch_size,
                            epochs=epochs,
                            validation_data=(x_test, y_test))

    conv1_weights = model.get_layer('conv1').get_weights()
    np.savez('conv1_weights.npz', W_conv=conv1_weights[0], b_conv=conv1_weights[1])

    np.savez('layer11_results.npz', acc=history.history['acc'], loss=history.history['loss'],
                 val_acc=history.history['val_acc'], val_loss=history.history['val_loss'])

    return model

def layer_stage1_helper(epochs, block):
    batch_size = 100
    num_classes = 10
    data_augmentation = True

    # The data, shuffled and split between train and test sets:
    (x_train, y_train), (x_test, y_test) = cifar10.load_data()
    print('x_train shape:', x_train.shape)
    print(x_train.shape[0], 'train samples')
    print(x_test.shape[0], 'test samples')

    # Convert class vectors to binary class matrices.
    y_train = keras.utils.to_categorical(y_train, num_classes)
    y_test = keras.utils.to_categorical(y_test, num_classes)

    main_input = Input(shape=x_train.shape[1:], name='main_input')

    x = Conv2D(64, (3,3), name='conv1', trainable=False, weights=load_conv_weights('conv1_weights.npz'))(main_input)
    for i in xrange(1, block):
        x = residual_block(x, 64, 1, i, trainable=False, weights=load_weights('weights_1{0}.npz'.format(i)))
    x = residual_block(x, 64, 1, block)

    flat = Flatten()(x)

    fc_weights = load_fc_weights("fc_weights_1{0}.npz".format(block-1))

    fc1 = Dense(512, activation='relu', name='fc1', weights=fc_weights[0])(flat)
    fc1_drop = Dropout(0.5)(fc1)
    main_output = Dense(10, activation='softmax', name='fc2', weights=fc_weights[1])(fc1_drop)

    model = Model(inputs=[main_input], outputs=[main_output])
    model.compile(optimizer='adam',
                  loss='categorical_crossentropy',
                  metrics=['accuracy'])

    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')
    x_train /= 255
    x_test /= 255

    if not data_augmentation:
        print('Not using data augmentation.')
        model.fit(x_train, y_train,
                  batch_size=batch_size,
                  epochs=epochs,
                  validation_data=(x_test, y_test),
                  shuffle=True)
    else:
        print('Using real-time data augmentation.')
        # This will do preprocessing and realtime data augmentation:
        datagen = ImageDataGenerator(
            featurewise_center=False,  # set input mean to 0 over the dataset
            samplewise_center=False,  # set each sample mean to 0
            featurewise_std_normalization=False,  # divide inputs by std of the dataset
            samplewise_std_normalization=False,  # divide each input by its std
            zca_whitening=False,  # apply ZCA whitening
            rotation_range=0,  # randomly rotate images in the range (degrees, 0 to 180)
            width_shift_range=0.1,  # randomly shift images horizontally (fraction of total width)
            height_shift_range=0.1,  # randomly shift images vertically (fraction of total height)
            horizontal_flip=True,  # randomly flip images
            vertical_flip=False)  # randomly flip images

        # Compute quantities required for feature-wise normalization
        # (std, mean, and principal components if ZCA whitening is applied).
        datagen.fit(x_train)

        # Fit the model on the batches generated by datagen.flow().
        history = model.fit_generator(datagen.flow(x_train, y_train,
                                         batch_size=batch_size),
                            steps_per_epoch=x_train.shape[0] // batch_size,
                            epochs=epochs,
                            validation_data=(x_test, y_test))

        np.savez('layer1{0}_results.npz'.format(block), acc=history.history['acc'], loss=history.history['loss'],
                 val_acc=history.history['val_acc'], val_loss=history.history['val_loss'])

    return model

def layer21(epochs):
    batch_size = 100
    num_classes = 10
    data_augmentation = True

    # The data, shuffled and split between train and test sets:
    (x_train, y_train), (x_test, y_test) = cifar10.load_data()
    print('x_train shape:', x_train.shape)
    print(x_train.shape[0], 'train samples')
    print(x_test.shape[0], 'test samples')

    # Convert class vectors to binary class matrices.
    y_train = keras.utils.to_categorical(y_train, num_classes)
    y_test = keras.utils.to_categorical(y_test, num_classes)

    main_input = Input(shape=x_train.shape[1:], name='main_input')

    # stage 1
    x = Conv2D(64, (3,3), name='conv1', trainable=False, weights=load_conv_weights('conv1_weights.npz'))(main_input)
    for i in xrange(1, 6):
        x = residual_block(x, 64, 1, i, trainable=False, weights=load_weights('weights_1{0}.npz'.format(i)))

    # stage 2
    pool1 = MaxPooling2D(pool_size=(2,2))(x)
    conv2 = Conv2D(128, (3,3), kernel_regularizer=l2(1e-6), name='conv2')(pool1)
    x = residual_block(conv2, 128, 2, 1)

    flat = Flatten()(x)

    fc1 = Dense(512, activation='relu', name='fc1')(flat)
    fc1_drop = Dropout(0.5)(fc1)
    main_output = Dense(10, activation='softmax', name='fc2')(fc1_drop)

    model = Model(inputs=[main_input], outputs=[main_output])
    model.compile(optimizer='adam',
                  loss='categorical_crossentropy',
                  metrics=['accuracy'])

    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')
    x_train /= 255
    x_test /= 255

    if not data_augmentation:
        print('Not using data augmentation.')
        model.fit(x_train, y_train,
                  batch_size=batch_size,
                  epochs=epochs,
                  validation_data=(x_test, y_test),
                  shuffle=True)
    else:
        print('Using real-time data augmentation.')
        # This will do preprocessing and realtime data augmentation:
        datagen = ImageDataGenerator(
            featurewise_center=False,  # set input mean to 0 over the dataset
            samplewise_center=False,  # set each sample mean to 0
            featurewise_std_normalization=False,  # divide inputs by std of the dataset
            samplewise_std_normalization=False,  # divide each input by its std
            zca_whitening=False,  # apply ZCA whitening
            rotation_range=0,  # randomly rotate images in the range (degrees, 0 to 180)
            width_shift_range=0.1,  # randomly shift images horizontally (fraction of total width)
            height_shift_range=0.1,  # randomly shift images vertically (fraction of total height)
            horizontal_flip=True,  # randomly flip images
            vertical_flip=False)  # randomly flip images

        # Compute quantities required for feature-wise normalization
        # (std, mean, and principal components if ZCA whitening is applied).
        datagen.fit(x_train)

        # Fit the model on the batches generated by datagen.flow().
        history = model.fit_generator(datagen.flow(x_train, y_train,
                                         batch_size=batch_size),
                            steps_per_epoch=x_train.shape[0] // batch_size,
                            epochs=epochs,
                            validation_data=(x_test, y_test))

    conv2_weights = model.get_layer('conv2').get_weights()
    np.savez('conv2_weights.npz', W_conv=conv2_weights[0], b_conv=conv2_weights[1])

    np.savez('layer21_results.npz', acc=history.history['acc'], loss=history.history['loss'],
                 val_acc=history.history['val_acc'], val_loss=history.history['val_loss'])

    return model

def layer_stage2_helper(epochs, block):
    batch_size = 100
    num_classes = 10
    data_augmentation = True

    # The data, shuffled and split between train and test sets:
    (x_train, y_train), (x_test, y_test) = cifar10.load_data()
    print('x_train shape:', x_train.shape)
    print(x_train.shape[0], 'train samples')
    print(x_test.shape[0], 'test samples')

    # Convert class vectors to binary class matrices.
    y_train = keras.utils.to_categorical(y_train, num_classes)
    y_test = keras.utils.to_categorical(y_test, num_classes)

    main_input = Input(shape=x_train.shape[1:], name='main_input')

    # stage 1
    x = Conv2D(64, (3,3), name='conv1', trainable=False, weights=load_conv_weights('conv1_weights.npz'))(main_input)
    for i in xrange(1, 6):
        x = residual_block(x, 64, 1, i, trainable=False, weights=load_weights('weights_1{0}.npz'.format(i)))

    # stage 2
    pool1 = MaxPooling2D(pool_size=(2,2))(x)
    x = Conv2D(128, (3,3), name='conv2', trainable=False, weights=load_conv_weights('conv2_weights.npz'))(pool1)
    for i in xrange(1, block):
        x = residual_block(x, 128, 2, i, trainable=False, weights=load_weights('weights_2{0}.npz'.format(i)))
    x = residual_block(x, 128, 2, block)

    flat = Flatten()(x)

    fc_weights = load_fc_weights("fc_weights_2{0}.npz".format(block-1))

    fc1 = Dense(512, activation='relu', name='fc1', weights=fc_weights[0])(flat)
    fc1_drop = Dropout(0.5)(fc1)
    main_output = Dense(10, activation='softmax', name='fc2', weights=fc_weights[1])(fc1_drop)

    model = Model(inputs=[main_input], outputs=[main_output])
    model.compile(optimizer='adam',
                  loss='categorical_crossentropy',
                  metrics=['accuracy'])
    model.get_layer('conv1').set_weights(load_conv_weights('conv1_weights.npz'))

    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')
    x_train /= 255
    x_test /= 255

    if not data_augmentation:
        print('Not using data augmentation.')
        model.fit(x_train, y_train,
                  batch_size=batch_size,
                  epochs=epochs,
                  validation_data=(x_test, y_test),
                  shuffle=True)
    else:
        print('Using real-time data augmentation.')
        # This will do preprocessing and realtime data augmentation:
        datagen = ImageDataGenerator(
            featurewise_center=False,  # set input mean to 0 over the dataset
            samplewise_center=False,  # set each sample mean to 0
            featurewise_std_normalization=False,  # divide inputs by std of the dataset
            samplewise_std_normalization=False,  # divide each input by its std
            zca_whitening=False,  # apply ZCA whitening
            rotation_range=0,  # randomly rotate images in the range (degrees, 0 to 180)
            width_shift_range=0.1,  # randomly shift images horizontally (fraction of total width)
            height_shift_range=0.1,  # randomly shift images vertically (fraction of total height)
            horizontal_flip=True,  # randomly flip images
            vertical_flip=False)  # randomly flip images

        # Compute quantities required for feature-wise normalization
        # (std, mean, and principal components if ZCA whitening is applied).
        datagen.fit(x_train)

        # Fit the model on the batches generated by datagen.flow().
        history = model.fit_generator(datagen.flow(x_train, y_train,
                                         batch_size=batch_size),
                            steps_per_epoch=x_train.shape[0] // batch_size,
                            epochs=epochs,
                            validation_data=(x_test, y_test))

    np.savez('layer2{0}_results.npz'.format(block), acc=history.history['acc'], loss=history.history['loss'],
                 val_acc=history.history['val_acc'], val_loss=history.history['val_loss'])


    return model

def layer31(epochs):
    batch_size = 100
    num_classes = 10
    data_augmentation = True

    # The data, shuffled and split between train and test sets:
    (x_train, y_train), (x_test, y_test) = cifar10.load_data()
    print('x_train shape:', x_train.shape)
    print(x_train.shape[0], 'train samples')
    print(x_test.shape[0], 'test samples')

    # Convert class vectors to binary class matrices.
    y_train = keras.utils.to_categorical(y_train, num_classes)
    y_test = keras.utils.to_categorical(y_test, num_classes)

    main_input = Input(shape=x_train.shape[1:], name='main_input')

    # stage 1
    x = Conv2D(64, (3,3), name='conv1', weights=load_conv_weights('conv1_weights.npz'), trainable=False)(main_input)
    for i in xrange(1, 6):
        x = residual_block(x, 64, 1, i, trainable=False, weights=load_weights('weights_1{0}.npz'.format(i)))

    x = MaxPooling2D(pool_size=(2,2))(x)
    x = Conv2D(128, (3,3), trainable=False, weights=load_conv_weights('weights_21.npz'), name='conv2')(x)
    for i in xrange(1, 6):
        x = residual_block(x, 128, 2, i, trainable=False, weights=load_weights('weights_2{0}.npz'.format(i)))

    pool2 = MaxPooling2D(pool_size=(2,2))(x)
    conv3 = Conv2D(256, (3,3), kernel_regularizer=l2(1e-6), name='conv3')(pool2)
    x = residual_block(conv3, 256, 3, 1)

    flat = Flatten()(x)

    fc1 = Dense(512, activation='relu', name='fc1')(flat)
    fc1_drop = Dropout(0.5)(fc1)
    main_output = Dense(10, activation='softmax', name='fc2')(fc1_drop)

    model = Model(inputs=[main_input], outputs=[main_output])
    model.compile(optimizer='adam',
                  loss='categorical_crossentropy',
                  metrics=['accuracy'])

    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')
    x_train /= 255
    x_test /= 255

    if not data_augmentation:
        print('Not using data augmentation.')
        model.fit(x_train, y_train,
                  batch_size=batch_size,
                  epochs=epochs,
                  validation_data=(x_test, y_test),
                  shuffle=True)
    else:
        print('Using real-time data augmentation.')
        # This will do preprocessing and realtime data augmentation:
        datagen = ImageDataGenerator(
            featurewise_center=False,  # set input mean to 0 over the dataset
            samplewise_center=False,  # set each sample mean to 0
            featurewise_std_normalization=False,  # divide inputs by std of the dataset
            samplewise_std_normalization=False,  # divide each input by its std
            zca_whitening=False,  # apply ZCA whitening
            rotation_range=0,  # randomly rotate images in the range (degrees, 0 to 180)
            width_shift_range=0.1,  # randomly shift images horizontally (fraction of total width)
            height_shift_range=0.1,  # randomly shift images vertically (fraction of total height)
            horizontal_flip=True,  # randomly flip images
            vertical_flip=False)  # randomly flip images

        # Compute quantities required for feature-wise normalization
        # (std, mean, and principal components if ZCA whitening is applied).
        datagen.fit(x_train)

        # Fit the model on the batches generated by datagen.flow().
        history = model.fit_generator(datagen.flow(x_train, y_train,
                                         batch_size=batch_size),
                            steps_per_epoch=x_train.shape[0] // batch_size,
                            epochs=epochs,
                            validation_data=(x_test, y_test))

        np.savez('layer31_results.npz', acc=history.history['acc'], loss=history.history['loss'],
                 val_acc=history.history['val_acc'], val_loss=history.history['val_loss'])

        conv3_weights = model.get_layer('conv3').get_weights()
        np.savez('conv3_weights.npz', W_conv=conv3_weights[0], b_conv=conv3_weights[1])

    return model


def layer_stage3_helper(epochs, block):
    batch_size = 100
    num_classes = 10
    data_augmentation = True

    # The data, shuffled and split between train and test sets:
    (x_train, y_train), (x_test, y_test) = cifar10.load_data()
    print('x_train shape:', x_train.shape)
    print(x_train.shape[0], 'train samples')
    print(x_test.shape[0], 'test samples')

    # Convert class vectors to binary class matrices.
    y_train = keras.utils.to_categorical(y_train, num_classes)
    y_test = keras.utils.to_categorical(y_test, num_classes)

    main_input = Input(shape=x_train.shape[1:], name='main_input')

    # stage 1
    x = Conv2D(64, (3,3), name='conv1', weights=load_conv_weights('conv1_weights.npz'), trainable=False)(main_input)
    for i in xrange(1, 6):
        x = residual_block(x, 64, 1, i, trainable=False, weights=load_weights('weights_1{0}.npz'.format(i)))

    pool1 = MaxPooling2D(pool_size=(2,2))(x)
    x = Conv2D(128, (3,3), trainable=False, weights=load_conv_weights('conv2_weights.npz'), name='conv2')(pool1)
    for i in xrange(1, 6):
        x = residual_block(x, 128, 2, i, trainable=False, weights=load_weights('weights_2{0}.npz'.format(i)))

    pool2 = MaxPooling2D(pool_size=(2,2))(x)
    x = Conv2D(256, (3,3), trainable=False, weights=load_conv_weights('conv3_weights.npz'), name='conv3')(pool2)
    for i in xrange(1, block):
        x = residual_block(x, 256, 3, i, trainable=False, weights=load_weights('weights_3{0}.npz'.format(i)))
    x = residual_block(x, 256, 3, block)

    flat = Flatten()(x)

    fc_weights = load_fc_weights("fc_weights_3{0}.npz".format(block-1))

    fc1 = Dense(512, activation='relu', name='fc1', weights=fc_weights[0])(flat)
    fc1_drop = Dropout(0.5)(fc1)
    main_output = Dense(10, activation='softmax', name='fc2', weights=fc_weights[1])(fc1_drop)

    model = Model(inputs=[main_input], outputs=[main_output])
    model.compile(optimizer='adam',
                  loss='categorical_crossentropy',
                  metrics=['accuracy'])
    model.get_layer('conv1').set_weights(load_conv_weights('conv1_weights.npz'))

    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')
    x_train /= 255
    x_test /= 255

    if not data_augmentation:
        print('Not using data augmentation.')
        model.fit(x_train, y_train,
                  batch_size=batch_size,
                  epochs=epochs,
                  validation_data=(x_test, y_test),
                  shuffle=True)
    else:
        print('Using real-time data augmentation.')
        # This will do preprocessing and realtime data augmentation:
        datagen = ImageDataGenerator(
            featurewise_center=False,  # set input mean to 0 over the dataset
            samplewise_center=False,  # set each sample mean to 0
            featurewise_std_normalization=False,  # divide inputs by std of the dataset
            samplewise_std_normalization=False,  # divide each input by its std
            zca_whitening=False,  # apply ZCA whitening
            rotation_range=0,  # randomly rotate images in the range (degrees, 0 to 180)
            width_shift_range=0.1,  # randomly shift images horizontally (fraction of total width)
            height_shift_range=0.1,  # randomly shift images vertically (fraction of total height)
            horizontal_flip=True,  # randomly flip images
            vertical_flip=False)  # randomly flip images

        # Compute quantities required for feature-wise normalization
        # (std, mean, and principal components if ZCA whitening is applied).
        datagen.fit(x_train)

        # Fit the model on the batches generated by datagen.flow().
        history = model.fit_generator(datagen.flow(x_train, y_train,
                                         batch_size=batch_size),
                            steps_per_epoch=x_train.shape[0] // batch_size,
                            epochs=epochs,
                            validation_data=(x_test, y_test))

    np.savez('layer3{0}_results.npz'.format(block), acc=history.history['acc'], loss=history.history['loss'],
                 val_acc=history.history['val_acc'], val_loss=history.history['val_loss'])


    return model

def layer(epochs, stage, block):
    if stage == 1:
        save_weights(layer_stage1_helper(epochs, block), 'weights_{0}{1}.npz'.format(stage, block), stage, block)
    if stage == 2:
        save_weights(layer_stage2_helper(epochs, block), 'weights_{0}{1}.npz'.format(stage, block), stage, block)
    if stage == 3:
        save_weights(layer_stage3_helper(epochs, block), 'weights_{0}{1}.npz'.format(stage, block), stage, block)

if __name__ == "__main__":
    save_weights(layer11(10), 'weights_11.npz', 1, 1)
    #layer(1,1,2)
    #layer(1,1,3)
    #layer(1,1,4)
    #layer(1,1,5)

    #save_weights(layer21(1), 'weights_21.npz', 2, 1)
    #layer(1,2,2)
    #layer(1,2,3)
    #layer(1,2,4)
    #layer(1,2,5)
